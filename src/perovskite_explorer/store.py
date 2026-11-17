from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .util import canonical, digest, now


class Store:
    """One writer (external FileLock); every page is a durable transaction."""

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "state.sqlite"
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, compound TEXT NOT NULL, source TEXT NOT NULL,
                query TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                cursor TEXT, payload TEXT NOT NULL DEFAULT '[]', total INTEGER,
                truncated INTEGER NOT NULL DEFAULT 0, error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS http_cache (
                key TEXT PRIMARY KEY, request TEXT NOT NULL, body BLOB NOT NULL,
                sha256 TEXT NOT NULL, content_type TEXT, fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, time TEXT NOT NULL, job_id TEXT, action TEXT NOT NULL, detail TEXT
            );
            CREATE TABLE IF NOT EXISTS reviews (
                compound TEXT NOT NULL, record_key TEXT NOT NULL, decision TEXT NOT NULL,
                reviewer TEXT NOT NULL, note TEXT NOT NULL, sample_id TEXT NOT NULL,
                replication_of TEXT NOT NULL, updated TEXT NOT NULL,
                PRIMARY KEY(compound, record_key)
            );
            CREATE TABLE IF NOT EXISTS local_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        version = self.get_meta("schema_version")
        if version not in (None, 1):
            raise ValueError(f"Versão do banco incompatível: {version}")
        self.set_meta("schema_version", 1)

    def get_meta(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_meta(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, canonical(value)))

    def event(self, action, detail="", job_id=None):
        with self.db:
            self.db.execute("INSERT INTO events(time,job_id,action,detail) VALUES (?,?,?,?)",
                            (now(), job_id, action, str(detail)))

    def add_job(self, compound, source, query, kind="search"):
        key = digest(canonical([compound, source, query, kind]))[:24]
        with self.db:
            self.db.execute("""INSERT OR IGNORE INTO jobs
                (id,compound,source,query,kind,updated) VALUES (?,?,?,?,?,?)""",
                            (key, compound, source, query, kind, now()))
        return key

    def jobs(self, kind=None):
        sql = "SELECT * FROM jobs" + (" WHERE kind=?" if kind else "") + " ORDER BY rowid"
        rows = self.db.execute(sql, (kind,) if kind else ()).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]

    def start(self, key):
        with self.db:
            self.db.execute("UPDATE jobs SET status='running',error=NULL,attempts=attempts+1,updated=? WHERE id=?",
                            (now(), key))

    def page(self, key, records, cursor, total, done=False, truncated=False):
        with self.db:
            row = self.db.execute("SELECT payload FROM jobs WHERE id=?", (key,)).fetchone()
            current = json.loads(row[0])
            # Retrying a page must never duplicate records.
            merged = {r["id"]: r for r in current}
            merged.update({r["id"]: r for r in records})
            self.db.execute("""UPDATE jobs SET payload=?,cursor=?,total=?,status=?,truncated=?,updated=?
                WHERE id=?""", (canonical(list(merged.values())), cursor, total,
                                "done" if done else "running", int(truncated), now(), key))

    def fail(self, key, error, status="failed"):
        with self.db:
            self.db.execute("UPDATE jobs SET status=?,error=?,updated=? WHERE id=?",
                            (status, str(error), now(), key))
        self.event(status, error, key)

    def recover(self):
        with self.db:
            self.db.execute("UPDATE jobs SET status='pending' WHERE status='running'")

    def backup(self):
        target = self.directory / ".backup.tmp.sqlite"
        with sqlite3.connect(target) as backup:
            self.db.backup(backup)
        with target.open("rb") as file:
            os.fsync(file.fileno())
        os.replace(target, self.directory / "state.backup.sqlite")

    def integrity(self):
        return self.db.execute("PRAGMA integrity_check").fetchone()[0]

    def close(self):
        self.db.close()
