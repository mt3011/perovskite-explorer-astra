from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from .http import NotFound, SourceError
from .util import digest, normalize

# Deliberately small, transparent dictionary. Different protonation states are search
# variants, not statements of chemical identity or of structural incorporation.
KNOWN = {
    "phenazine": {"aliases": ["phenazine"], "family_aliases": ["phenazinium", "phenazine-5,10-diium"]},
    "niacinamide": {"aliases": ["nicotinamide", "pyridine-3-carboxamide"],
                    "family_aliases": ["nicotinamidium"]},
    "nicotinamide": {"aliases": ["niacinamide", "pyridine-3-carboxamide"],
                     "family_aliases": ["nicotinamidium"]},
    "theobromine": {"aliases": ["3,7-dimethylxanthine"], "family_aliases": ["theobrominium"]},
    "3-aminobenzoic acid": {"aliases": ["m-aminobenzoic acid"],
                            "family_aliases": ["3-aminobenzoate", "3-carboxyanilinium"]},
    "nicotinic acid": {"aliases": ["pyridine-3-carboxylic acid"],
                       "family_aliases": ["nicotinate", "3-carboxypyridinium"]},
    "4-aminophenyl sulfone": {
        "ambiguous": True,
        "note": "Nome incompleto/ambíguo. Confira estrutura, CAS ou CID; não se presume dapsona."
    },
}


def read_compounds(path: Path, overrides=None):
    results, seen = [], set()
    overrides = overrides or {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        name = line.strip().rstrip("\\").strip()
        if not name or name.startswith("#"):
            continue
        if len(name) > 300 or any(c in name for c in ('"', '\t', '\x00')):
            raise ValueError(f"Linha {number}: use um nome por linha, sem aspas ou tabulações.")
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)
        custom = overrides.get(name, {})
        info = KNOWN.get(key, {}) | custom
        aliases = list(dict.fromkeys([name, *info.get("aliases", [])]))
        family = list(dict.fromkeys(info.get("family_aliases", [])))
        if any(not isinstance(a, str) or len(a) < 3 or len(a) > 200 or '"' in a for a in aliases + family):
            raise ValueError(f"Alias inválido para {name}.")
        results.append({"id": digest(key)[:16], "name": name, "aliases": aliases,
                        "family_aliases": family, "ambiguous": info.get("ambiguous", False),
                        "note": info.get("note", ""), "cid": info.get("cid"),
                        "identity_reviewed": info.get("identity_reviewed", False)})
    if not results:
        raise ValueError("Lista vazia. Informe um composto por linha.")
    return results


def resolve(compound, http):
    result = dict(compound) | {"status": "unresolved", "properties": {}, "suggested_synonyms": []}
    if compound["ambiguous"]:
        return result | {"status": "ambiguous"}
    base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
    if compound.get("cid"):
        cids = [int(compound["cid"])]
    else:
        try:
            response = http.json(f"{base}/name/{quote(compound['name'], safe='')}/cids/JSON")
        except NotFound:
            return result | {"note": "PubChem não resolveu o nome; revise CAS/CID e sinônimos."}
        cids = response.get("IdentifierList", {}).get("CID", [])
    result["candidate_cids"] = cids
    if len(cids) != 1:
        return result | {"status": "ambiguous", "note": "PubChem retornou zero ou múltiplos CIDs; revise."}
    cid = cids[0]
    fields = "MolecularFormula,MolecularWeight,InChIKey,ConnectivitySMILES,IUPACName,Charge,XLogP,TPSA"
    data = http.json(f"{base}/cid/{cid}/property/{fields}/JSON")
    props = data.get("PropertyTable", {}).get("Properties", [])
    if not props:
        raise SourceError("PubChem: propriedades ausentes; contrato inesperado.")
    result.update({"cid": cid, "status": "reviewed" if compound["identity_reviewed"] else "resolved_unreviewed",
                   "properties": props[0], "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"})
    try:
        synonyms = http.json(f"{base}/cid/{cid}/synonyms/JSON")["InformationList"]["Information"][0]["Synonym"]
        result["suggested_synonyms"] = synonyms[:30]
        result["cas_candidates"] = [s for s in synonyms if re.fullmatch(r"\d{2,7}-\d{2}-\d", s)]
    except (SourceError, KeyError, IndexError):
        result["synonym_warning"] = "Sinônimos PubChem indisponíveis; nomes de entrada preservados."
    return result
