from __future__ import annotations

import json
import os
import platform
import signal
import xml.etree.ElementTree as ET
from importlib.metadata import version
from pathlib import Path

from filelock import FileLock

from . import RULES_VERSION, __version__
from .analysis import evidence
from .http import HttpClient, SourceError
from .identity import read_compounds, resolve
from .sources import SOURCES, csd_search, fetch_page, queries
from .store import Store
from .structures import obtain_structure
from .util import atomic_write, canonical, digest, now, write_json

DEFAULTS = {"sources": ["cod", "hybrid3", "crossref", "openalex", "europepmc"],
            "max_results": 100, "max_hybrid3_records": 10000, "page_size": 50,
            "max_aliases": 6, "timeout": 30, "retries": 3, "interval": 0.5,
            "download_cifs": True, "fulltext": True, "max_fulltexts": 100,
            "extra_terms": [], "follow_dois": True}


def validate_config(config):
    unknown = set(config) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Opções desconhecidas: {', '.join(sorted(unknown))}")
    config = DEFAULTS | config
    if not config["sources"] or set(config["sources"]) - SOURCES:
        raise ValueError("Selecione fontes válidas: " + ", ".join(sorted(SOURCES)))
    for key in ("max_results", "max_hybrid3_records", "page_size", "max_aliases", "timeout", "retries", "max_fulltexts"):
        if not isinstance(config[key], int) or config[key] < 1:
            raise ValueError(f"{key} deve ser inteiro positivo.")
    if config["page_size"] > 100 or config["retries"] > 5 or config["interval"] < 0:
        raise ValueError("Use page_size <= 100, retries <= 5 e interval >= 0.")
    if any(not isinstance(t, str) or '"' in t for t in config["extra_terms"]):
        raise ValueError("extra_terms deve conter textos sem aspas.")
    return config


def initialize(directory, input_path, config, overrides=None):
    config = validate_config(config)
    compounds = read_compounds(input_path, overrides)
    manifest = {"version": __version__, "rules_version": RULES_VERSION, "config": config,
                "compounds": compounds, "input_sha256": digest(input_path.read_bytes()),
                "created_at": now(), "python": platform.python_version(),
                "dependencies": {p: version(p) for p in ("requests", "gemmi", "filelock")},
                "credentials": {"openalex_key_present": bool(os.getenv("OPENALEX_API_KEY")),
                                "email_present": bool(os.getenv("PEROVSKITE_EMAIL"))}}
    directory.mkdir(parents=True, exist_ok=True)
    with FileLock(str(directory / ".run.lock"), timeout=0):
        if (directory / "manifest.json").exists() or (directory / "state.sqlite").exists():
            raise ValueError("Pasta de execução já existe. Use resume ou escolha outra pasta.")
        write_json(directory / "manifest.json", manifest)
        atomic_write(directory / "input.txt", input_path.read_bytes())
        with_store = Store(directory)
        try:
            with_store.set_meta("manifest", manifest)
            with_store.event("initialized", f"{len(compounds)} compostos")
            for compound in compounds:
                with_store.add_job(compound["id"], "pubchem", compound["name"], "identity")
            with_store.backup()
        finally:
            with_store.close()
    return manifest


def identities(store):
    manifest = store.get_meta("manifest")
    resolved = {j["compound"]: j["payload"][0] for j in store.jobs("identity") if j["payload"]}
    return [c | resolved.get(c["id"], {"status": "unresolved", "properties": {}}) for c in manifest["compounds"]]


def collected_records(store, compound_id=None):
    rows = []
    for job in store.jobs():
        if job["kind"] not in {"search", "doi_search"}:
            continue
        if compound_id and job["compound"] not in (compound_id, "__all__"):
            continue
        rows.extend(job["payload"])
    rows.extend(json.loads(r[0]) for r in store.db.execute("SELECT payload FROM local_records"))
    # The same source record can be found by several aliases or by its DOI.
    unique = {r["id"]: dict(r) for r in rows}
    cifs = {r["id"]: r for j in store.jobs("cif") for r in j["payload"]}
    texts = {r["id"]: r for j in store.jobs("fulltext") for r in j["payload"]}
    for item in unique.values():
        item["structures"] = [s | cifs.get(s["id"], {}) for s in item.get("structures", [])]
        pmcid = item.get("metadata", {}).get("pmcid")
        if pmcid in texts:
            item["fulltext"] = texts[pmcid]["text"]
            item["fulltext_provenance"] = texts[pmcid]["provenance"]
    return list(unique.values())


def fulltext(pmcid, http):
    import re
    if not re.fullmatch(r"PMC\d+", pmcid):
        raise SourceError("Identificador PMC inválido.")
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    body = http.get(url)
    # Disallow entities before parsing; never resolve external DTDs or entities.
    if b"<!ENTITY" in body.upper():
        raise SourceError("XML com entidades não é aceito.")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise SourceError("XML de texto integral inválido.") from None
    paragraphs = []
    body_node = root.find(".//body")
    if body_node is not None:
        for parent in body_node.iter():
            for child in list(parent):
                if child.tag in {"ref-list", "ack", "back"}:
                    parent.remove(child)
        paragraphs = [" ".join(p.itertext()) for p in body_node.iter("p")]
    return {"id": pmcid, "text": "\n".join(paragraphs),
            "provenance": {"url": url, "sha256": digest(body), "sections": "body/p; references excluded"}}


def plan_searches(store, compounds, config):
    for source in config["sources"]:
        if source == "hybrid3":
            store.add_job("__all__", source, "all datasets")
            continue
        for compound in compounds:
            aliases = list(dict.fromkeys(compound["aliases"] + compound["family_aliases"]))
            for query in queries(source, aliases[:config["max_aliases"]], config["extra_terms"]):
                store.add_job(compound["id"], source, query)


def run(directory: Path, offline=False, log=print):
    directory = directory.resolve()
    with FileLock(str(directory / ".run.lock"), timeout=0):
        store = Store(directory)
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        interrupted = False
        try:
            manifest = store.get_meta("manifest")
            if not manifest:
                raise ValueError("Manifesto ausente. Inicie uma execução com run.")
            if manifest["version"] != __version__ or manifest["rules_version"] != RULES_VERSION:
                raise ValueError("Versão da execução difere do programa; preserve esta versão ou inicie nova pasta.")
            if store.integrity() != "ok":
                raise ValueError("Integridade SQLite falhou. Use restore em uma pasta nova.")
            store.recover()
            config = manifest["config"]
            http = HttpClient(store, offline=offline, timeout=config["timeout"], retries=config["retries"],
                              interval=config["interval"], email=os.getenv("PEROVSKITE_EMAIL", ""))
            compounds = {c["id"]: c for c in manifest["compounds"]}
            completed = 0

            def execute(kinds):
                nonlocal completed
                for job in store.jobs():
                    if job["kind"] not in kinds or job["status"] == "done":
                        continue
                    store.start(job["id"])
                    log(f"[{job['source']}] {job['query'][:110]}", flush=True)
                    try:
                        if job["kind"] == "identity":
                            item = resolve(compounds[job["compound"]], http)
                            store.page(job["id"], [item], None, 1, True)
                        elif job["kind"] == "cif":
                            item = obtain_structure(json.loads(job["query"]), directory, http)
                            store.page(job["id"], [item], None, 1, True)
                        elif job["kind"] == "fulltext":
                            store.page(job["id"], [fulltext(job["query"], http)], None, 1, True)
                        elif job["source"] == "csd":
                            page = csd_search(job["query"], directory, config["max_results"])
                            store.page(job["id"], page.records, page.cursor, page.total, page.done, page.truncated)
                        else:
                            cursor, seen = job["cursor"], len(job["payload"])
                            while True:
                                page = fetch_page(job["source"], job["query"], cursor, seen, http, config)
                                store.page(job["id"], page.records, page.cursor, page.total, page.done, page.truncated)
                                if page.done:
                                    break
                                cursor, seen = page.cursor, seen + len(page.records)
                        completed += 1
                    except (SourceError, ValueError, KeyError, TypeError, IndexError, RuntimeError) as exc:
                        # SDK errors may contain paths; external URLs with keys are never logged.
                        message = str(exc) if isinstance(exc, SourceError) else f"{type(exc).__name__}: contrato/dados inesperados."
                        store.fail(job["id"], message)
                        log(f"  Pendente: {message}", flush=True)
                    if completed % 10 == 0:
                        store.backup()
            execute({"identity"})
            resolved = identities(store)
            plan_searches(store, resolved, config)
            execute({"search"})
            if config["fulltext"]:
                pmcids = sorted({r["metadata"]["pmcid"] for r in collected_records(store)
                                 if r.get("metadata", {}).get("pmcid") and r["metadata"].get("is_open_access")})
                store.set_meta("fulltext_coverage", {"eligible": len(pmcids), "planned": min(len(pmcids), config["max_fulltexts"])})
                for pmcid in pmcids[:config["max_fulltexts"]]:
                    store.add_job("__all__", "europepmc", pmcid, "fulltext")
                execute({"fulltext"})
            if config["follow_dois"] and "cod" in config["sources"]:
                for compound in resolved:
                    for rec in collected_records(store, compound["id"]):
                        if rec.get("doi") and evidence(rec, compound)["status"] in {"structural_candidate", "mixed_evidence"}:
                            store.add_job(compound["id"], "cod", "doi:" + rec["doi"], "doi_search")
                execute({"doi_search"})
            if config["download_cifs"]:
                for compound in resolved:
                    for rec in collected_records(store, compound["id"]):
                        ev = evidence(rec, compound)
                        if not ev["matched_aliases"] or not ev["scope_match"]:
                            continue
                        for structure in rec.get("structures", []):
                            # Avoid re-keying already enriched structures on resume.
                            base = {k: v for k, v in structure.items() if k not in {"cif", "preview", "availability", "note"}}
                            if structure.get("url"):
                                base.pop("path", None)
                            store.add_job("__all__", "cif", canonical(base), "cif")
                execute({"cif"})
            store.event("run_finished")
        except KeyboardInterrupt:
            interrupted = True
            store.event("interrupted", "Retome com o comando resume.")
            log("Interrompido: páginas concluídas preservadas; gerando relatório parcial.", flush=True)
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            if store.get_meta("manifest"):
                from .report import export_report
                export_report(store)
                store.backup()
            store.close()
        return 130 if interrupted else 0
