from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

from .util import canonical, digest, now


class SourceError(RuntimeError):
    pass


class NotFound(SourceError):
    pass


class Unavailable(SourceError):
    pass


class HttpClient:
    def __init__(self, store, offline=False, timeout=30, retries=3, interval=0.5, email=""):
        self.store = store
        self.offline = offline
        self.timeout = timeout
        self.retries = retries
        self.interval = interval
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"PerovskiteExplorerAstra/0.1 (research; {email or 'local user'})"
        self.last_request = {}

    def get(self, url, params=None, headers=None):
        if urlsplit(url).scheme != "https":
            raise SourceError("Somente HTTPS é permitido para fontes remotas.")
        # Credentials never enter logs, manifests, request hashes or cache metadata.
        public_params = {k: v for k, v in (params or {}).items()
                         if k.lower() not in {"api_key", "token", "key", "access_token"}}
        request = canonical({"url": url, "params": public_params})
        key = digest(request)
        row = self.store.db.execute("SELECT * FROM http_cache WHERE key=?", (key,)).fetchone()
        if row and digest(row["body"]) == row["sha256"]:
            return bytes(row["body"])
        if row:
            self.store.event("cache_corrupt", key)
        if self.offline:
            raise Unavailable("Resposta ausente ou corrompida no cache; modo offline.")
        host = urlsplit(url).netloc
        for attempt in range(self.retries):
            delay = max(0.0, self.interval - (time.monotonic() - self.last_request.get(host, 0)))
            time.sleep(delay)
            self.last_request[host] = time.monotonic()
            try:
                with self.session.get(url, params=params, headers=headers, timeout=(10, self.timeout),
                                      stream=True) as response:
                    if response.status_code == 404:
                        raise NotFound(f"HTTP 404 em {host}.")
                    if response.status_code in {401, 403}:
                        raise Unavailable(f"HTTP {response.status_code} em {host}; confira acesso/chave/licença.")
                    if response.status_code == 429 or response.status_code >= 500:
                        wait = self.retry_delay(response.headers.get("Retry-After"), attempt)
                        if attempt + 1 == self.retries or wait > 60:
                            raise Unavailable(f"HTTP {response.status_code} em {host}; retome mais tarde.")
                        time.sleep(wait)
                        continue
                    if not response.ok:
                        raise SourceError(f"HTTP {response.status_code} em {host}; consulta não concluída.")
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 40 * 1024 * 1024:
                            raise SourceError("Resposta excede 40 MiB; restrinja a consulta.")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    with self.store.db:
                        self.store.db.execute("INSERT OR REPLACE INTO http_cache VALUES (?,?,?,?,?,?)",
                                              (key, request, body, digest(body),
                                               response.headers.get("Content-Type", ""), now()))
                    return body
            except requests.RequestException as exc:
                if attempt + 1 == self.retries:
                    # str(exc) can contain an authenticated URL. Only log its type.
                    raise Unavailable(f"{type(exc).__name__} em {host}; sem resposta válida.") from None
                time.sleep(2 ** attempt)
        raise Unavailable(f"Tentativas esgotadas em {host}.")

    @staticmethod
    def retry_delay(value, attempt):
        if value:
            try:
                return max(0, float(value))
            except ValueError:
                try:
                    return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError):
                    pass
        return 2 ** attempt

    def json(self, url, params=None, headers=None):
        body = self.get(url, params, headers)
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise SourceError(f"Resposta não é JSON válido em {urlsplit(url).netloc}.") from None
