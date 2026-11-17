import json
import sqlite3

import pytest

from perovskite_explorer.http import HttpClient, Unavailable
from perovskite_explorer.pipeline import run
from perovskite_explorer.sources import Page, record
from perovskite_explorer.util import canonical, digest, now


def test_page_commit_recovery_and_backup(store):
    job = store.add_job("compound", "test", "query")
    store.start(job)
    store.page(job, [{"id": "one"}], "page2", 2)
    store.recover()
    current = next(j for j in store.jobs() if j["id"] == job)
    assert current["status"] == "pending"
    assert current["cursor"] == "page2"
    store.page(job, [{"id": "one"}, {"id": "two"}], None, 2, True)
    store.backup()
    with sqlite3.connect(store.directory / "state.backup.sqlite") as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert len(json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (job,)).fetchone()[0])) == 2


def test_corrupt_cache_is_not_silently_used(store):
    request = canonical({"url": "https://example.org/data", "params": {}})
    with store.db:
        store.db.execute("INSERT INTO http_cache VALUES (?,?,?,?,?,?)",
                         (digest(request), request, b"corrupt", digest(b"expected"), "application/json", now()))
    with pytest.raises(Unavailable):
        HttpClient(store, offline=True).json("https://example.org/data")


def test_api_keys_never_in_cache_metadata(store, monkeypatch):
    class Response:
        status_code, ok, headers = 200, True, {}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_content(self, size):
            yield b'{"ok":true}'
    client = HttpClient(store, interval=0)
    monkeypatch.setattr(client.session, "get", lambda *a, **k: Response())
    assert client.json("https://example.org/data", {"api_key": "secret", "page": 1}) == {"ok": True}
    assert "secret" not in store.db.execute("SELECT request FROM http_cache").fetchone()[0]


def test_kill_mid_search_resume_no_repeat_completed_pages(store, monkeypatch):
    import perovskite_explorer.pipeline as pipeline
    monkeypatch.setattr(pipeline, "resolve", lambda c, h: c | {"status": "resolved_unreviewed", "properties": {}})
    cursors = []
    interrupted = False
    def fetch(source, query, cursor, seen, http, config):
        nonlocal interrupted
        cursors.append((query, cursor))
        if cursor is None:
            return Page([record("test", query + "1", title="Phenazine perovskite")], "two", 2, False)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return Page([record("test", query + "2", title="Phenazine additive perovskite")], None, 2, True)
    monkeypatch.setattr(pipeline, "fetch_page", fetch)
    def silent(*a, **kw):
        pass
    assert run(store.directory, log=silent) == 130
    assert (store.directory / "report.html").is_file()
    assert run(store.directory, log=silent) == 0
    first_query = cursors[0][0]
    assert cursors.count((first_query, None)) == 1
    assert cursors.count((first_query, "two")) == 2
    assert all(j["status"] == "done" for j in store.jobs())
    assert store.integrity() == "ok"


def test_rate_limit_long_wait_is_deferred(store, monkeypatch):
    class Response:
        status_code, headers = 429, {"Retry-After": "3600"}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    client = HttpClient(store, interval=0)
    monkeypatch.setattr(client.session, "get", lambda *a, **k: Response())
    with pytest.raises(Unavailable, match="429"):
        client.get("https://example.org/data")
