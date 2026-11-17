from __future__ import annotations

import csv
import re

from .analysis import deduplicate
from .pipeline import collected_records
from .sources import record
from .structures import inspect_cif
from .util import atomic_write, canonical, digest, doi_normalize, now, safe_filename


def import_files(store, cif=None, text=None, doi="", title="", chemical_name="", year=None):
    if not cif and not text:
        raise ValueError("Informe --cif e/ou --text.")
    if doi and not doi_normalize(doi):
        raise ValueError("DOI inválido.")
    data, structures, body, metadata = [], [], "", {"chemical_name": chemical_name}
    for source in (cif, text):
        if source:
            data.append(source.read_bytes())
    identifier = digest(b"\x00".join(data) + canonical([doi, title, chemical_name, year]).encode())[:24]
    if cif:
        target = store.directory / "structures" / ("local_" + identifier + ".cif")
        atomic_write(target, cif.read_bytes())
        info = inspect_cif(target)
        structures = [{"id": "local:" + identifier, "source": "local", "url": "",
                       "path": str(target.relative_to(store.directory)), "cif": info,
                       "chemical_name": chemical_name or info["blocks"][0]["chemical_name"],
                       "formula": info["blocks"][0]["formula"]}]
        doi = doi or next((b["doi"] for b in info["blocks"] if b["doi"]), "")
        metadata["formula"] = info["blocks"][0]["formula"]
    if text:
        target = store.directory / "documents" / (identifier + "_" + safe_filename(text.name))
        atomic_write(target, text.read_bytes())
        if text.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                raise ValueError("Instale o extra PDF: pip install '.[pdf]'.") from None
            body = "\n".join(page.extract_text() or "" for page in PdfReader(text).pages)
            if len(body.strip()) < 80:
                raise ValueError("PDF sem texto extraível. Faça OCR local e importe TXT; nenhum OCR/IA é chamado.")
        else:
            body = text.read_text(encoding="utf-8-sig")
        body = re.split(r"(?im)^\s*(?:references|bibliography|referências)\s*$", body)[0]
        metadata["document"] = {"path": str(target.relative_to(store.directory)), "sha256": digest(text.read_bytes()),
                                "reference_removal": "Corte na primeira seção References/Bibliography/Referências isolada."}
    rec = record("local", identifier, kind="structure" if cif else "publication", title=title,
                 doi=doi_normalize(doi), year=year, type="imported", fulltext=body,
                 url="https://doi.org/" + doi_normalize(doi) if doi else "",
                 structures=structures, metadata=metadata)
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO local_records VALUES (?,?)", (rec["id"], canonical(rec)))
    store.event("import", rec["id"])
    return rec["id"]


DECISIONS = {"structural_confirmed", "nonstructural_confirmed", "excluded", "uncertain"}


def import_reviews(store, path):
    compounds = {c["id"] for c in store.get_meta("manifest")["compounds"]}
    keys = {w["key"] for w in deduplicate(collected_records(store))}
    pending = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for n, row in enumerate(csv.DictReader(handle), 2):
            decision = row.get("decision", "").strip()
            if not decision:
                continue
            if decision not in DECISIONS:
                raise ValueError(f"Linha {n}: decisão inválida.")
            if row.get("compound_id") not in compounds or row.get("record_key") not in keys:
                raise ValueError(f"Linha {n}: composto/registro não existe nesta execução.")
            if not row.get("reviewer", "").strip() or len(row.get("note", "").strip()) < 10:
                raise ValueError(f"Linha {n}: informe revisor e justificativa com evidência/página.")
            if decision == "structural_confirmed" and not row.get("sample_id", "").strip():
                raise ValueError(f"Linha {n}: confirmação estrutural exige sample_id da fase/amostra.")
            if row.get("replication_of") and (decision != "structural_confirmed" or not row["record_key"].startswith("doi:")):
                raise ValueError(f"Linha {n}: reprodução exige confirmação estrutural de um trabalho com DOI.")
            pending[(row["compound_id"], row["record_key"])] = {k: row.get(k, "").strip() for k in
                ("compound_id", "record_key", "decision", "reviewer", "note", "sample_id", "replication_of")}
    # Validate every row before writing any decision; target may be in the same import.
    existing = {(r["compound"], r["record_key"]): dict(r) for r in store.db.execute("SELECT * FROM reviews")}
    merged = existing | pending
    for key, row in merged.items():
        if row.get("replication_of"):
            target_key = (key[0], row["replication_of"])
            target = merged.get(target_key)
            if target_key == key or not target or target["decision"] != "structural_confirmed" or target["sample_id"] != row["sample_id"]:
                raise ValueError("replication_of deve apontar para outro registro confirmado da mesma fase/composto.")
            chain, seen = target, {key}
            while chain.get("replication_of"):
                following = (key[0], chain["replication_of"])
                if following in seen:
                    raise ValueError("Ciclo entre reproduções; confira os vínculos.")
                seen.add(following)
                chain = merged.get(following, {})
    with store.db:
        for key, row in pending.items():
            previous = existing.get(key)
            store.db.execute("INSERT INTO events(time,job_id,action,detail) VALUES (?,?,?,?)",
                             (now(), None, "review", canonical({"previous": previous, "new": row})))
            store.db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?,?,?)",
                             (key[0], key[1], row["decision"], row["reviewer"], row["note"],
                              row["sample_id"], row["replication_of"], now()))
    return len(pending)
