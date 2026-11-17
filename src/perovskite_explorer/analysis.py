"""Conservative, explainable rules. Automatic decisions are never confirmations."""
from __future__ import annotations

import re

from .structures import HALIDES, METALS, elements
from .util import digest, doi_normalize, mentions, normalize, plain

SCOPE_RE = re.compile(r"perovskit|anti.?perovskit|metal.{0,8}halide|organic.{0,5}inorganic|semiconduct|"
                      r"coordination polymer|\b(?:lead|tin|bismuth|antimony|copper|silver|manganese|zinc) "
                      r"(?:iodide|bromide|chloride)", re.I)
STRUCTURAL_RE = re.compile(r"(?:organic|spacer|interlayer|counter)[ -]?(?:cation|anion|ligand)|"
                           r"(?:cation|anion|ligand)s? (?:in|of|within|between)|"
                           r"crystal structure.{0,50}(?:of|contain)|incorporat.{0,50}(?:lattice|framework)|"
                           r"(?:forms?|formed|synthesi[sz]ed).{0,60}(?:hybrid|perovskit|crystal)|"
                           r"(?:hybrid|perovskit).{0,45}(?:crystals?|structures?)", re.I)
NONSTRUCTURAL_RE = re.compile(r"passivat|additive|hole.transport|electron.transport|interfacial|"
                              r"interface modif|surface modif|surface treatment|dopant|sensiti[sz]er", re.I)
NEGATION_RE = re.compile(r"\b(?:not|no|never|without|unable|cannot|failed to|doesn't|isn't)\b|"
                         r"rather than|not incorporated|absence of", re.I)
HYPOTHESIS_RE = re.compile(r"\b(?:could|might|may|proposed|potential|hypothes|suggest|predicted|simulation|"
                           r"calculated|theoretical|density functional|dft)\b", re.I)
PROPERTY_RE = re.compile(r"band.?gap|photoluminescen|quantum yield|exciton|conductiv|mobility|"
                         r"absorpt|emission|stability|dielectric|ferroelect|photoconduct", re.I)
DIMENSION_RE = re.compile(r"\b([0123])\s*[- ]?D\b|\b(zero|one|two|three)[ -]dimensional", re.I)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip()]


def evidence(record, compound):
    aliases = compound["aliases"] + compound["family_aliases"]
    metadata = record.get("metadata", {})
    system = metadata.get("system", {})
    names = " ".join(str(x or "") for x in [metadata.get("chemical_name"), metadata.get("common_name"),
                     *metadata.get("synonyms", []), system.get("compound_name"), system.get("group"),
                     system.get("iupac"), system.get("organic")])
    for structure in record.get("structures", []):
        names += " " + str(structure.get("chemical_name") or "")
        names += " " + " ".join(b.get("chemical_name", "") for b in structure.get("cif", {}).get("blocks", []))
    # Reference lists in full text are excluded at import/retrieval, not used for rules.
    text = plain(record.get("title", "")) + ". " + plain(record.get("abstract", ""))
    local_text = record.get("fulltext", "")
    segments = [("title_abstract", s) for s in sentences(text)] + [("fulltext", s) for s in sentences(local_text)]
    matched = mentions(text + " " + names + " " + local_text, aliases)
    name_hits = mentions(names, aliases)
    formula = metadata.get("formula") or system.get("formula") or " ".join(
        str(s.get("formula") or "") for s in record.get("structures", []))
    el = elements(formula)
    hybrid = "C" in el and bool(el & METALS)
    scope = bool(SCOPE_RE.search(text + " " + names + " " + local_text)) or hybrid
    supporting, nonstructural, uncertain, properties = [], [], [], []
    semiconductor_context = False
    dimensions = set()
    for location, sentence in segments:
        if not mentions(sentence, aliases):
            continue
        if PROPERTY_RE.search(sentence):
            properties.append({"text": sentence[:1000], "location": location,
                               "attribution": "Contexto com nome; valor/atribuição à fase requer revisão."})
        if re.search(r"semiconduct|band.?gap|photoluminescen|photoconduct", sentence, re.I):
            semiconductor_context = True
        if NONSTRUCTURAL_RE.search(sentence):
            nonstructural.append({"text": sentence[:800], "location": location})
        if STRUCTURAL_RE.search(sentence) and scope:
            item = {"text": sentence[:800], "location": location}
            if NEGATION_RE.search(sentence) or HYPOTHESIS_RE.search(sentence):
                uncertain.append(item)
            else:
                supporting.append(item)
                for match in DIMENSION_RE.finditer(sentence):
                    dimensions.add(match.group(1) or str(["zero", "one", "two", "three"].index(match.group(2).lower())))
    warnings = []
    if not matched:
        status = "no_exact_mention"
    elif record.get("kind") == "structure" and formula and not hybrid:
        status = "outside_scope"
        warnings.append("Composição do depósito não indica híbrido com carbono e metal/metaloide selecionado.")
    elif not scope:
        status = "outside_scope"
    elif record.get("type") == "review" or "review" in normalize(record.get("title", "")):
        status = "review_context"
    elif metadata.get("is_experimental") is False or record.get("type") in {"preprint", "posted-content"}:
        status = "prediction_or_preprint"
    elif name_hits and hybrid:
        status = "structural_candidate"
        supporting.append({"text": names.strip()[:800], "location": "crystal_metadata"})
        warnings.append("Nome em metadados + composição híbrida; confirmar componente e função (inclui solvatos).")
    elif supporting and nonstructural:
        status = "mixed_evidence"
    elif supporting:
        status = "structural_candidate"
    elif nonstructural:
        status = "nonstructural_use"
    else:
        status = "mention_only"
    if metadata.get("is_retracted") or metadata.get("update_to"):
        warnings.append("Retratação/atualização indicada pela fonte; conferir artigo.")
        status = "publication_alert"
    if compound.get("ambiguous"):
        warnings.append("Identidade de entrada ambígua: não priorizar sem correção.")
    if not record.get("abstract") and not local_text:
        warnings.append("Sem resumo/texto integral disponível; análise limitada ao título e metadados.")
    if name_hits and hybrid and not bool(el & HALIDES):
        warnings.append("Candidato híbrido sem halogênio identificado; pode ser complexo/MOF fora do interesse.")
    if system.get("dimensionality") in (0, 1, 2, 2.5, 3):
        dimensions.add(str(system["dimensionality"]))
    return {"status": status, "matched_aliases": matched,
            "family_matches": [x for x in matched if x in compound["family_aliases"]],
            "supporting": supporting, "nonstructural": nonstructural, "uncertain": uncertain,
            "properties_context": properties, "reported_dimensions": sorted(dimensions),
            "warnings": warnings, "scope_match": scope,
            "interest": {"metal_halide_composition": hybrid and bool(el & HALIDES),
                         "semiconductor_context": semiconductor_context,
                         "hybrid3_curated_dataset": record.get("source") == "hybrid3",
                         "note": "Indicadores para organizar leitura; não comprovam semicondutividade."}}


def work_key(record):
    doi = doi_normalize(record.get("doi"))
    if doi:
        return "doi:" + doi
    # Do not merge by title alone: no-DOI records are provisional identities.
    return record["id"]


def deduplicate(records):
    groups = {}
    for rec in records:
        key = work_key(rec)
        if key not in groups:
            groups[key] = {"key": key, "doi": doi_normalize(rec.get("doi")), "records": [], "ids": set()}
        if rec["id"] not in groups[key]["ids"]:
            groups[key]["records"].append(rec)
            groups[key]["ids"].add(rec["id"])
    result = []
    for group in groups.values():
        group.pop("ids")
        group["title"] = max((r.get("title", "") for r in group["records"]), key=len, default="")
        group["year"] = min((int(r["year"]) for r in group["records"] if str(r.get("year", "")).isdigit()), default=None)
        group["sources"] = sorted({r["source"] for r in group["records"]})
        group["duplicate_title_hint"] = digest(normalize(group["title"]).rstrip("."))[:16]
        group["publication_eligible"] = any(
            r["type"] not in {"component", "dataset", "computed-dataset", "review", "preprint", "posted-content"}
            for r in group["records"])
        # Dataset/CIF citation DOI is a bibliographic link, not an extra article.
        if group["doi"] and any(r["kind"] in {"structure", "dataset"} and r["type"] != "computed-dataset"
                                 for r in group["records"]):
            group["publication_eligible"] = True
        result.append(group)
    return sorted(result, key=lambda x: (x["year"] or 0, x["key"]), reverse=True)


def assess_work(work, compound, review=None):
    analyses = [evidence(rec, compound) for rec in work["records"]]
    priority = ["publication_alert", "mixed_evidence", "structural_candidate", "nonstructural_use",
                "prediction_or_preprint", "review_context", "mention_only", "outside_scope", "no_exact_mention"]
    statuses = {a["status"] for a in analyses}
    status = next(p for p in priority if p in statuses)
    if "structural_candidate" in statuses and "nonstructural_use" in statuses:
        status = "mixed_evidence"
    if review:
        status = review["decision"]
    return work | {"classification": status, "evidence": analyses, "review": review,
                   "has_exact_mention": any(a["matched_aliases"] for a in analyses),
                   "scope_match": any(a["scope_match"] for a in analyses)}


def chemical_descriptors(identity):
    smiles = identity.get("properties", {}).get("ConnectivitySMILES")
    if not smiles:
        return {"available": False, "reason": "SMILES não resolvido."}
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, Lipinski
    except ImportError:
        return {"available": False, "reason": "RDKit opcional não instalado; pip install '.[chem]'."}
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return {"available": False, "reason": "SMILES inválido para RDKit."}
    return {"available": True, "hbond_donors": Lipinski.NumHDonors(molecule),
            "hbond_acceptors": Lipinski.NumHAcceptors(molecule), "rotatable_bonds": Lipinski.NumRotatableBonds(molecule),
            "aromatic_rings": Lipinski.NumAromaticRings(molecule), "tpsa": Descriptors.TPSA(molecule),
            "note": "Descritores da forma resolvida; não predizem formação de fase, pKa ou band gap."}
