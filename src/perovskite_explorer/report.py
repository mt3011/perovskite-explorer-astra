from __future__ import annotations

import csv
import html
import io
import json
from collections import defaultdict
from urllib.parse import quote

from . import RULES_VERSION, __version__
from .analysis import assess_work, chemical_descriptors, deduplicate
from .pipeline import collected_records, identities
from .util import atomic_write, now, safe_url, write_json

LABELS = {
    "structural_confirmed": "Estrutural — confirmado por revisão",
    "structural_candidate": "Uso estrutural candidato — revisar",
    "mixed_evidence": "Evidência mista — revisar fase e função",
    "nonstructural_use": "Indícios de aditivo/passivação/transporte",
    "nonstructural_confirmed": "Uso não estrutural — revisado",
    "mention_only": "Somente menção / função indefinida",
    "no_exact_mention": "Nome não localizado no texto disponível",
    "outside_scope": "Fora do escopo pelas regras atuais",
    "review_context": "Contexto de revisão bibliográfica",
    "prediction_or_preprint": "Cálculo ou preprint — revisar",
    "publication_alert": "Alerta editorial — revisar",
    "excluded": "Excluído por revisão", "uncertain": "Indeterminado após revisão",
}


def csv_text(rows, fields=None):
    out = io.StringIO(newline="")
    fields = fields or (list(rows[0]) if rows else [])
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Neutralize spreadsheet formula injection from provider/user strings.
        cleaned = {k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
                   for k, v in row.items()}
        writer.writerow(cleaned)
    return "\ufeff" + out.getvalue()


def build_report(store):
    manifest = store.get_meta("manifest")
    jobs = store.jobs()
    reviews = {(r["compound"], r["record_key"]): dict(r) for r in store.db.execute("SELECT * FROM reviews")}
    reports = []
    for compound in identities(store):
        cid = compound["id"]
        works = [assess_work(w, compound, reviews.get((cid, w["key"])))
                 for w in deduplicate(collected_records(store, cid))]
        screened_without_mention = sum(not w["has_exact_mention"] and not w["review"] for w in works)
        works = [w for w in works if w["has_exact_mention"] or w["review"]]
        related_jobs = [j for j in jobs if j["compound"] in (cid, "__all__")]
        failed = [j for j in related_jobs if j["status"] != "done"]
        truncated = [j for j in related_jobs if j["truncated"]]
        alias_count = len(set(compound["aliases"] + compound["family_aliases"]))
        aliases_limited = alias_count > manifest["config"]["max_aliases"]
        confirmed = [w for w in works if w["classification"] == "structural_confirmed"]
        candidates = [w for w in works if w["classification"] == "structural_candidate"]
        confirmed_dois = {w["doi"] for w in confirmed if w["doi"] and w["publication_eligible"]}
        candidate_dois = {w["doi"] for w in candidates if w["doi"] and w["publication_eligible"]}
        samples = defaultdict(list)
        for w in confirmed:
            samples[w["review"]["sample_id"]].append(w)
        sample_rows = []
        for sample, entries in samples.items():
            sample_rows.append({"sample_id": sample, "distinct_dois": len({w["doi"] for w in entries if w["doi"]}),
                                "works": [w["key"] for w in entries],
                                "reviewed_replications": len({w["doi"] for w in entries if w["doi"] and w["review"]["replication_of"]})})
        coverage_ok = not failed and not truncated and not aliases_limited
        if compound["status"] in {"ambiguous", "unresolved"}:
            recommendation = "Resolver identidade antes de priorizar"
        elif confirmed_dois and len(confirmed_dois) <= 3:
            recommendation = "Uso estrutural revisado pouco reportado no conjunto recuperado"
        elif confirmed_dois:
            recommendation = "Uso estrutural revisado; comparar fases e lacunas experimentais"
        elif candidate_dois:
            recommendation = "Revisar candidatos estruturais e possível baixa frequência"
        elif not coverage_ok:
            recommendation = "Cobertura incompleta: ampliar busca antes de avaliar novidade"
        else:
            recommendation = "Sem confirmação estrutural nesta busca; investigar, sem alegar ineditismo"
        years = [w["year"] for w in confirmed if w["year"]]
        structure_ids = {s["id"] for w in works for r in w["records"] for s in r["structures"]}
        valid_cifs = {s.get("cif", {}).get("sha256") for w in works for r in w["records"] for s in r["structures"]
                      if s.get("cif", {}).get("valid_structure")}
        counts = {"works_with_exact_mention": len(works), "screened_without_exact_mention": screened_without_mention,
                  "candidate_structural_dois": len(candidate_dois), "confirmed_structural_dois": len(confirmed_dois),
                  "structural_records_without_doi": sum(not w["doi"] for w in confirmed + candidates),
                  "structure_entries": len(structure_ids), "distinct_cif_files": len(valid_cifs),
                  "reviewed_samples": len(samples), "reviewed_replications": sum(s["reviewed_replications"] for s in sample_rows),
                  "first_confirmed_year": min(years) if years else None,
                  "last_confirmed_year": max(years) if years else None}
        reports.append({"compound": compound, "descriptors": chemical_descriptors(compound),
                        "counts": counts, "recommendation": recommendation, "works": works, "samples": sample_rows,
                        "coverage": {"planned_queries_finished": coverage_ok, "failed_or_pending": len(failed),
                                     "truncated_queries": len(truncated), "aliases_limited": aliases_limited,
                                     "csd_searched": "csd" in manifest["config"]["sources"],
                                     "warning": "Contagens são limites inferiores do conjunto recuperado; não medem toda a literatura."}})
    return {"generated_at": now(), "version": __version__, "rules_version": RULES_VERSION,
            "manifest": manifest, "compounds": reports,
            "jobs": [{k: v for k, v in j.items() if k != "payload"} | {"retrieved": len(j["payload"])} for j in jobs],
            "fulltext_coverage": store.get_meta("fulltext_coverage"),
            "notes": ["Sem IA. Classificação automática não equivale a confirmação experimental.",
                      "Citações, artigos, depósitos, fases e reproduções são grandezas distintas.",
                      "Nenhum resultado ou fonte indisponível não demonstra ausência na literatura.",
                      "Mesmo DOI é unido; registros sem DOI permanecem separados, com pista de título duplicado.",
                      "Contagem de CIF por hash não identifica polimorfos ou estruturas cristalograficamente equivalentes."]}


def link(url, label):
    clean = safe_url(url)
    return f'<a href="{html.escape(clean, quote=True)}" target="_blank" rel="noopener">{html.escape(label)}</a>' if clean else html.escape(label)


def local_link(path, label):
    # Generated reports only use paths inside the run directory.
    if not path or path.startswith(("/", "\\")) or ".." in path.split("/"):
        return ""
    return f'<a href="{html.escape(quote(path, safe="/"), quote=True)}">{html.escape(label)}</a>'


def render_html(report):
    esc = html.escape
    cards = []
    summary_rows = []
    for item in report["compounds"]:
        compound, counts = item["compound"], item["counts"]
        name, cid = compound["name"], compound["id"]
        coverage = item["coverage"]
        summary_rows.append(f'<tr><td><a href="#{cid}">{esc(name)}</a></td><td>{counts["confirmed_structural_dois"]}</td>'
                            f'<td>{counts["candidate_structural_dois"]}</td><td>{counts["distinct_cif_files"]}</td>'
                            f'<td>{coverage["failed_or_pending"]} / {coverage["truncated_queries"]}</td><td>{esc(item["recommendation"])}</td></tr>')
        work_cards = []
        for work in item["works"]:
            evidence_parts, structure_parts, seen_structures = [], [], set()
            for rec, ev in zip(work["records"], work["evidence"]):
                snippets = ev["supporting"] + ev["nonstructural"] + ev["uncertain"]
                excerpts = "".join(f'<blockquote>{esc(s["text"])}<small>{esc(s["location"])}</small></blockquote>' for s in snippets[:8])
                properties = "".join(f'<blockquote>{esc(s["text"])}<small>Propriedade — atribuição à fase requer conferência</small></blockquote>'
                                     for s in ev["properties_context"][:5])
                cites = f' · citações nesta fonte: {rec["citations"]}' if rec.get("citations") is not None else ""
                evidence_parts.append(f'<div class="evidence"><b>{esc(rec["source"])}</b>{esc(cites)} · {link(rec["url"], "registro")}'
                                      f'<p>{esc(", ".join(ev["matched_aliases"]) or "Nome não localizado")}</p>{excerpts}{properties}'
                                      f'<p class="muted">{esc(" ".join(ev["warnings"]))}</p></div>')
                for structure in rec["structures"]:
                    if structure["id"] in seen_structures:
                        continue
                    seen_structures.add(structure["id"])
                    cif = structure.get("cif", {})
                    metadata = {k: v for k, v in structure.items() if k not in {"cif", "preview"}}
                    blocks = [{k: v for k, v in b.items() if k != "preview_atoms"} for b in cif.get("blocks", [])]
                    preview = ""
                    if structure.get("preview"):
                        preview = f'<img loading="lazy" class="crystal" src="{esc(quote(structure["preview"], safe="/"))}" alt="Projeção da unidade assimétrica"/>'
                    availability = "CIF disponível" if cif.get("valid_structure") else "Estrutura completa ainda não disponível/validada"
                    structure_parts.append(f'<div class="structure"><b>{esc(structure["id"])}</b> · {availability}<br>'
                                           f'{local_link(structure.get("path"), "Abrir/baixar CIF")} {link(structure.get("url", ""), "Fonte CIF")}'
                                           f'{preview}<details><summary>Dados cristalográficos</summary><pre>{esc(json.dumps(metadata | {"blocks": blocks}, ensure_ascii=False, indent=2))}</pre></details></div>')
            doi_url = "https://doi.org/" + work["doi"] if work["doi"] else ""
            review_text = f'<p>Revisão: {esc(json.dumps(work["review"], ensure_ascii=False))}</p>' if work["review"] else ""
            csd = link("https://www.ccdc.cam.ac.uk/structures/", "Consultar CCDC Access Structures pelo DOI") if work["doi"] else ""
            work_cards.append(f'<details class="work" data-status="{esc(work["classification"])}"><summary>'
                              f'<span class="badge">{esc(LABELS[work["classification"]])}</span> '
                              f'{esc(work["title"] or work["key"])} <small>{work["year"] or "ano desconhecido"}</small></summary>'
                              f'<p>{link(doi_url, work["doi"] or "Sem DOI")} · {esc(", ".join(work["sources"]))}</p>{csd}{review_text}'
                              + "".join(structure_parts + evidence_parts) + '</details>')
        identity = {k: v for k, v in compound.items() if k not in {"suggested_synonyms"}}
        cards.append(f'<section id="{cid}" class="compound"><h2>{esc(name)}</h2><p>{esc(item["recommendation"])}</p>'
                     f'<p class="muted">Identidade: {esc(compound["status"])} · {esc(compound.get("note", ""))}</p>'
                     f'<p>{counts["works_with_exact_mention"]} trabalhos/registros com menção exata; '
                     f'{counts["screened_without_exact_mention"]} resultados sem nome no texto disponível. '
                     f'Reproduções revisadas: {counts["reviewed_replications"]} (não revisado ≠ inexistente).</p>'
                     f'<details><summary>Identidade, descritores e amostras revisadas</summary><pre>{esc(json.dumps({"identity": identity, "descriptors": item["descriptors"], "samples": item["samples"]}, ensure_ascii=False, indent=2))}</pre></details>'
                     + "".join(work_cards) + '</section>')
    failed_jobs = [j for j in report["jobs"] if j["status"] != "done" or j["truncated"]]
    job_rows = "".join(f'<tr><td>{esc(j["source"])}</td><td>{esc(j["query"][:170])}</td><td>{esc(j["status"])}</td>'
                       f'<td>{j["retrieved"]}</td><td>{j["total"] if j["total"] is not None else "?"}</td>'
                       f'<td>{esc(j["error"] or ("Limite atingido" if j["truncated"] else ""))}</td></tr>' for j in failed_jobs)
    options = "".join(f'<option value="{key}">{esc(value)}</option>' for key, value in LABELS.items())
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Perovskite Explorer Astra — relatório</title><style>
:root{{font-family:system-ui,sans-serif;color:#183146;background:#f0f4f7}}body{{margin:auto;max-width:1250px;padding:30px}}h1{{font-size:2.2rem}}h2{{color:#0f6065}}
header,.compound,.coverage{{background:white;padding:24px;margin:20px 0;border:1px solid #dbe3e8;border-radius:12px}}a{{color:#096a8c}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:12px;border-bottom:1px solid #dde4ea;vertical-align:top}}.table-wrap{{overflow:auto}}th{{font-size:.85rem}}.muted,small{{color:#596c78}}small{{display:block}}
.notice{{padding:16px;background:#fff5d6;border-left:4px solid #c18818}}input,select{{padding:12px;border:1px solid #a3b5c0;border-radius:6px;max-width:100%;font:inherit}}
.filters{{position:sticky;top:0;background:#f0f4f7;padding:12px 0;z-index:1;display:flex;gap:12px;flex-wrap:wrap}}.work{{border-top:1px solid #dbe3e8;padding:16px 0}}
summary{{cursor:pointer;line-height:1.6}}.badge{{display:inline-block;font-size:.75rem;background:#e0eeee;padding:3px 8px;border-radius:4px;margin-right:8px}}blockquote{{margin:14px 0;padding:12px;border-left:3px solid #719fa9;background:#f6f9fa}}
.evidence{{margin-top:20px}}.structure{{display:inline-block;vertical-align:top;max-width:100%;padding:14px;background:#f8fafc;margin:10px 10px 10px 0}}.crystal{{display:block;width:340px;max-width:100%}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.8rem}}[hidden]{{display:none!important}}
@media(max-width:600px){{body{{padding:12px}}header,.compound{{padding:16px}}h1{{font-size:1.6rem}}}}@media print{{.filters{{display:none}}details>*{{display:block}}}}</style></head><body>
<header><small>PESQUISA DE SEMICONDUTORES HÍBRIDOS · SEM IA</small><h1>Perovskite Explorer Astra</h1><p>Relatório gerado em {esc(report['generated_at'])} · regras {esc(report['rules_version'])}</p>
<div class="notice">Ausência de evidência não comprova ineditismo. Candidatos automáticos exigem revisão de identidade, fase e função do orgânico. Artigos e citações não contam reproduções experimentais.</div>
<p>{local_link('summary.csv', 'Resumo CSV')} · {local_link('results.json', 'Resultados JSON')} · {local_link('queries.csv', 'Auditoria das consultas')} · {local_link('review_template.csv', 'Planilha de revisão')}</p></header>
<div class="table-wrap"><table><thead><tr><th>Orgânico</th><th>DOIs estruturais revisados</th><th>DOIs candidatos</th><th>CIFs distintos</th><th>Pendências / limites</th><th>Próxima ação</th></tr></thead><tbody>{''.join(summary_rows)}</tbody></table></div>
<section class="coverage"><details><summary>Cobertura e consultas incompletas ({len(failed_jobs)})</summary><p>Totais das fontes são resultados brutos, inclusive busca aproximada no Crossref; não são frequência de uso estrutural. Veja todas as consultas em queries.csv.</p><div class="table-wrap"><table><tr><th>Fonte</th><th>Consulta</th><th>Estado</th><th>Obtidos</th><th>Total bruto</th><th>Lacuna</th></tr>{job_rows}</table></div></details><p>Fontes selecionadas: {esc(', '.join(report['manifest']['config']['sources']))}. CSD exige instalação/licença e seleção explícita.</p></section>
<div class="filters"><input id="search" aria-label="Filtrar resultados" placeholder="Filtrar por composto, título, DOI…"><select id="status" aria-label="Filtrar classificação"><option value="">Todas as classificações</option>{options}</select></div>
{''.join(cards)}<footer><p>Abra o CIF no Mercury ou VESTA para inspecionar simetria e conectividade. A miniatura mostra somente uma projeção dos sítios da unidade assimétrica.</p></footer>
<script>const search=document.getElementById('search'),status=document.getElementById('status');function filter(){{const q=search.value.toLocaleLowerCase();document.querySelectorAll('.compound').forEach(c=>{{let visible=0;const name=c.querySelector('h2').textContent.toLocaleLowerCase();c.querySelectorAll('.work').forEach(w=>{{const show=(!q||name.includes(q)||w.textContent.toLocaleLowerCase().includes(q))&&(!status.value||w.dataset.status===status.value);w.hidden=!show;if(show)visible++;}});c.hidden=!!(q||status.value)&&!visible&&!name.includes(q);}});}}search.addEventListener('input',filter);status.addEventListener('change',filter);</script></body></html>'''


def export_report(store):
    report = build_report(store)
    directory = store.directory
    write_json(directory / "results.json", report)
    rows, review_rows = [], []
    for item in report["compounds"]:
        compound = item["compound"]
        rows.append({"compound": compound["name"], "identity_status": compound["status"], **item["counts"],
                     "pending_queries": item["coverage"]["failed_or_pending"],
                     "truncated_queries": item["coverage"]["truncated_queries"], "recommendation": item["recommendation"]})
        for work in item["works"]:
            review_rows.append({"compound_id": compound["id"], "compound": compound["name"], "record_key": work["key"],
                                "title": work["title"], "automatic_classification": work["classification"],
                                "decision": "", "reviewer": "", "note": "", "sample_id": "", "replication_of": ""})
    atomic_write(directory / "summary.csv", csv_text(rows))
    atomic_write(directory / "review_template.csv", csv_text(review_rows, ["compound_id", "compound", "record_key", "title",
                 "automatic_classification", "decision", "reviewer", "note", "sample_id", "replication_of"]))
    atomic_write(directory / "queries.csv", csv_text(report["jobs"], ["id", "compound", "source", "kind", "query", "status",
                 "retrieved", "total", "truncated", "error", "attempts", "updated"]))
    atomic_write(directory / "report.html", render_html(report))
    return report
