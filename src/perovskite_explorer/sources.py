"""Public, documented APIs only. Parsers retain source-specific metadata."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit

from .http import SourceError, Unavailable
from .util import doi_normalize, plain

SOURCES = {"cod", "hybrid3", "crossref", "openalex", "europepmc", "csd"}
SCOPE = ['perovskite', 'antiperovskite', '"metal halide"', '"organic-inorganic"',
         'semiconductor', '"coordination polymer"']


@dataclass
class Page:
    records: list[dict]
    cursor: str | None
    total: int | None
    done: bool
    truncated: bool = False


def record(source, identifier, **kwargs):
    return {"id": f"{source}:{identifier}", "source": source, "source_id": str(identifier),
            "kind": "publication", "title": "", "abstract": "", "doi": "", "year": None,
            "authors": [], "type": "unknown", "url": "", "citations": None,
            "structures": [], "metadata": {}, **kwargs}


def rebuild_abstract(index):
    if not isinstance(index, dict):
        return ""
    positions = {p: token for token, values in index.items() for p in values if isinstance(p, int)}
    return " ".join(positions[p] for p in sorted(positions))


def parse_crossref(item):
    dates = item.get("published", item.get("issued", {})).get("date-parts", [[None]])
    return record("crossref", item["DOI"], title=plain(" ".join(item.get("title", []))),
                  abstract=plain(item.get("abstract")), doi=doi_normalize(item["DOI"]),
                  year=dates[0][0] if dates and dates[0] else None,
                  authors=[plain(f"{a.get('given', '')} {a.get('family', '')}") for a in item.get("author", [])],
                  type=item.get("type", "unknown"), url=item.get("URL", ""),
                  citations=item.get("is-referenced-by-count"),
                  metadata={"relation": item.get("relation", {}), "links": item.get("link", []),
                            "journal": item.get("container-title", []),
                            "update_to": item.get("update-to", [])})


def parse_openalex(item):
    return record("openalex", item["id"], title=plain(item.get("title")),
                  abstract=rebuild_abstract(item.get("abstract_inverted_index")),
                  doi=doi_normalize(item.get("doi")), year=item.get("publication_year"),
                  authors=[a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])],
                  type=item.get("type", "unknown"), url=item.get("doi") or item["id"],
                  citations=item.get("cited_by_count"), metadata={
                      "is_retracted": item.get("is_retracted", False),
                      "open_access": item.get("open_access", {}), "ids": item.get("ids", {}),
                      "locations": item.get("locations", []),
                  })


def parse_europepmc(item):
    types = item.get("pubTypeList", {}).get("pubType", [])
    return record("europepmc", f"{item['source']}:{item['id']}", title=plain(item.get("title")),
                  abstract=plain(item.get("abstractText")), doi=doi_normalize(item.get("doi")),
                  year=int(item["pubYear"]) if str(item.get("pubYear", "")).isdigit() else None,
                  authors=[a.get("fullName", "") for a in item.get("authorList", {}).get("author", [])],
                  type="review" if any("review" in t.lower() for t in types) else "journal-article",
                  url=f"https://europepmc.org/article/{item['source']}/{item['id']}",
                  citations=item.get("citedByCount"), metadata={
                      "pmcid": item.get("pmcid"), "is_open_access": item.get("isOpenAccess") == "Y",
                      "publication_types": types,
                      "is_retracted": any("retract" in t.lower() for t in types),
                      "fulltext_urls": item.get("fullTextUrlList", {}),
                  })


def parse_cod(item):
    identifier = str(item["file"])
    return record("cod", identifier, kind="structure", title=plain(item.get("title")),
                  doi=doi_normalize(item.get("doi")), year=int(item["year"]) if item.get("year") else None,
                  authors=(item.get("authors") or "").split(";"), type="crystal-structure",
                  url=f"https://www.crystallography.net/cod/{identifier}.html",
                  structures=[{"id": f"COD:{identifier}", "source": "cod",
                               "url": f"https://www.crystallography.net/cod/{identifier}.cif",
                               "formula": item.get("formula"), "space_group": item.get("sg"),
                               "chemical_name": item.get("chemname") or item.get("commonname") or "",
                               "cell": {k: item.get(k) for k in ("a", "b", "c", "alpha", "beta", "gamma", "vol")}}],
                  metadata={"chemical_name": item.get("chemname"), "common_name": item.get("commonname"),
                            "formula": item.get("formula"), "duplicate_of": item.get("duplicateof"),
                            "flags": item.get("flags"), "r_factor": item.get("Robs")})


def _cif_links(value):
    result = []
    if isinstance(value, dict):
        for child in value.values():
            result.extend(_cif_links(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_cif_links(child))
    elif isinstance(value, str) and value.lower().split("?")[0].endswith(".cif"):
        if value.startswith(("https://", "/")):
            result.append(urljoin("https://materials.hybrid3.duke.edu/", value))
    return list(dict.fromkeys(result))


def parse_hybrid3(item):
    system = dict(item.get("system") or {})
    # DatasetSerializer embeds the raw Django choice, unlike SystemSerializer.
    # Upstream mapping: 0→0D, 1→1D, 2→2D, 3→2.5D, 4→3D.
    raw_dimension = system.get("dimensionality")
    system["dimensionality_source_code"] = raw_dimension
    system["dimensionality"] = {0: 0, 1: 1, 2: 2, 3: 2.5, 4: 3}.get(raw_dimension)
    reference = item.get("reference") or {}
    prop = item.get("primary_property") or {}
    structure = {"id": f"HybriD3:{system.get('id', item['pk'])}", "source": "hybrid3",
                 "chemical_name": system.get("compound_name", ""), "formula": system.get("formula"),
                 "space_group": item.get("space_group"), "dimensionality": system.get("dimensionality"),
                 "system_id": system.get("id"), "url": ""}
    cifs = _cif_links(item)
    structures = [structure | {"url": url, "id": structure["id"] + f":{i}"} for i, url in enumerate(cifs)]
    if not structures:
        structures = [structure]
    return record("hybrid3", item["pk"], kind="dataset", title=plain(reference.get("title")),
                  abstract=plain(item.get("caption")), doi=doi_normalize(reference.get("doi_isbn")),
                  year=int(reference["year"]) if str(reference.get("year", "")).isdigit() else None,
                  type="experimental-dataset" if item.get("is_experimental") else "computed-dataset",
                  url=f"https://materials.hybrid3.duke.edu/materials/dataset/{item['pk']}",
                  structures=structures, metadata={
                      "system": system, "property": prop, "unit": item.get("primary_unit"),
                      "secondary_property": item.get("secondary_property"), "secondary_unit": item.get("secondary_unit"),
                      "sample_type": item.get("sample_type"), "extraction_method": item.get("extraction_method"),
                      "subsets": item.get("subsets", []), "is_experimental": item.get("is_experimental"),
                      "verified_by": item.get("verified_by", []), "synthesis": item.get("synthesis", []),
                      "experimental": item.get("experimental", []), "computational": item.get("computational", []),
                      "reference": reference,
                  })


def queries(source, aliases, extra_terms=()):
    if source in {"cod", "csd"}:
        return aliases
    if source == "hybrid3":
        return ["all datasets"]
    if source == "crossref":
        # Crossref search is ranked, not a Boolean/exact compound filter.
        return [f'"{alias}" {topic}' for alias in aliases
                for topic in ["perovskite", "hybrid metal halide", "semiconductor coordination polymer", *extra_terms]]
    scope = " OR ".join([*SCOPE, *(f'"{t}"' for t in extra_terms)])
    return [f'"{alias}" AND ({scope})' for alias in aliases]


def fetch_page(source, query, cursor, seen, http, config):
    limit = config["max_results"] if source != "hybrid3" else config["max_hybrid3_records"]
    size = min(config["page_size"], limit - seen)
    if size < 1:
        return Page([], cursor, None, True, True)
    if source == "cod":
        params = {"doi" if query.startswith("doi:") else "text": query.removeprefix("doi:"), "format": "json"}
        data = http.json("https://www.crystallography.net/cod/result", params)
        if not isinstance(data, list):
            raise SourceError("COD: resposta inesperada; esperada lista JSON.")
        # API has no documented offset; record explicit client-side truncation.
        return Page([parse_cod(x) for x in data[:limit]], None, len(data), True, len(data) > limit)
    if source == "crossref":
        params = {"query.bibliographic": query, "rows": size, "cursor": cursor or "*"}
        if os.getenv("PEROVSKITE_EMAIL"):
            params["mailto"] = os.environ["PEROVSKITE_EMAIL"]
        data = http.json("https://api.crossref.org/works", params)["message"]
        items, total, next_cursor = data["items"], data["total-results"], data.get("next-cursor")
        parser = parse_crossref
        natural_end = len(items) < size or seen + len(items) >= total
    elif source == "openalex":
        token = os.getenv("OPENALEX_API_KEY")
        params = {"search": query, "per-page": size}
        if token:
            params.update({"api_key": token, "cursor": cursor or "*"})
        elif cursor:
            raise Unavailable("OpenAlex: paginação exige OPENALEX_API_KEY. Primeira página preservada.")
        data = http.json("https://api.openalex.org/works", params)
        items, total = data["results"], data["meta"]["count"]
        next_cursor = data["meta"].get("next_cursor") or ("requires-key" if not token else None)
        parser = parse_openalex
        natural_end = not items or seen + len(items) >= total
    elif source == "europepmc":
        data = http.json("https://www.ebi.ac.uk/europepmc/webservices/rest/search", {
            "query": query, "format": "json", "resultType": "core", "pageSize": size,
            "cursorMark": cursor or "*", "synonym": "false"})
        items, total = data["resultList"]["result"], data["hitCount"]
        next_cursor, parser = data.get("nextCursorMark"), parse_europepmc
        natural_end = not items or seen + len(items) >= total
    elif source == "hybrid3":
        # Cursor is a documented next-page URL. Enforce origin before following it.
        url = cursor or "https://materials.hybrid3.duke.edu/materials/datasets/"
        if urlsplit(url).netloc != "materials.hybrid3.duke.edu":
            raise SourceError("HybriD³ retornou paginação para domínio inesperado.")
        # Large spectral datasets make 50-row pages time out on the live service.
        # Reduce size while preserving the exact offset of an existing checkpoint.
        params = None if cursor else {"page_size": min(25, config["page_size"])}
        if cursor:
            parts = urlsplit(url)
            query_params = parse_qs(parts.query)
            old_size = int(query_params.get("page_size", [config["page_size"]])[0])
            old_page = int(query_params.get("page", ["1"])[0])
            if old_size > 25:
                new_size = max(n for n in range(1, 26) if old_size % n == 0)
                query_params["page_size"] = [str(new_size)]
                query_params["page"] = [str((old_page - 1) * old_size // new_size + 1)]
                url = urlunsplit(parts._replace(query=urlencode(query_params, doseq=True)))
        data = http.json(url, params)
        items, total, next_cursor = data["results"], data["count"], data["next"]
        parser, natural_end = parse_hybrid3, not next_cursor
        if len(items) > limit - seen:
            items = items[:limit - seen]
            natural_end = False
    else:
        raise ValueError(f"Fonte desconhecida: {source}")
    at_limit = seen + len(items) >= limit
    if not natural_end and not at_limit and (not next_cursor or next_cursor == cursor):
        raise SourceError(f"{source}: paginação incompleta ou repetida; resultados anteriores preservados.")
    return Page([parser(x) for x in items], next_cursor, total,
                natural_end or at_limit, at_limit and not natural_end)


def csd_search(query, directory, limit):
    """Optional local CSD Python API; no invented remote CCDC endpoint."""
    try:
        from ccdc.search import TextNumericSearch
    except ImportError:
        raise Unavailable("CSD: SDK ccdc ausente. Instale/ative o CSD Python API oficial com licença.") from None
    from .util import atomic_write, safe_filename

    search = TextNumericSearch()
    search.add_compound_name(query)
    # Fetch one extra to make truncation explicit; the API bounds hit collection.
    hits = search.search(max_hit_structures=limit + 1)
    records = []
    for hit in hits[:limit]:
        entry = hit.entry
        publication = entry.publication
        path = directory / "structures" / ("CSD_" + safe_filename(hit.identifier) + ".cif")
        atomic_write(path, entry.crystal.to_string("cif"))
        records.append(record("csd", hit.identifier, kind="structure",
                              title=plain(getattr(publication, "title", "")),
                              doi=doi_normalize(getattr(publication, "doi", "")),
                              year=getattr(publication, "year", None), type="crystal-structure",
                              url="https://www.ccdc.cam.ac.uk/structures/Search?Ccdcid=" + quote(hit.identifier),
                              structures=[{"id": f"CSD:{hit.identifier}", "source": "csd", "url": "",
                                           "path": str(path.relative_to(directory)),
                                           "chemical_name": entry.chemical_name, "formula": entry.molecule.formula}],
                              metadata={"chemical_name": entry.chemical_name,
                                        "synonyms": list(entry.synonyms), "licensed": True}))
    return Page(records, None, None, True, len(hits) > limit)
