import csv
import io

import pytest

from perovskite_explorer.local import import_files, import_reviews
from perovskite_explorer.report import build_report, csv_text, export_report
from perovskite_explorer.sources import record


def add_records(store):
    compound = store.get_meta("manifest")["compounds"][0]
    job = store.add_job(compound["id"], "crossref", "test")
    records = [record("crossref", "one", doi="10.1234/one", title="Phenazine organic cation in a hybrid perovskite.",
                      type="journal-article"),
               record("europepmc", "two", doi="10.1234/one", title="Phenazine organic cation in a hybrid perovskite.",
                      type="journal-article"),
               record("crossref", "three", doi="10.1234/two", title="Phenazine organic cation in a hybrid perovskite.",
                      type="journal-article")]
    store.page(job, records, None, 3, True)
    return compound


def review_csv(store, compound, decisions):
    path = store.directory / "decisions.csv"
    rows = [{"compound_id": compound["id"], "record_key": key, "decision": "structural_confirmed",
             "reviewer": "Test reviewer", "note": "Synthetic test decision; not scientific evidence.",
             "sample_id": "phase_A", "replication_of": replication} for key, replication in decisions]
    path.write_text(csv_text(rows), encoding="utf-8")
    return path


def test_review_counts_articles_and_replications_separately(store):
    compound = add_records(store)
    before = build_report(store)["compounds"][0]["counts"]
    assert before["confirmed_structural_dois"] == 0
    assert before["candidate_structural_dois"] == 2
    path = review_csv(store, compound, [("doi:10.1234/one", ""), ("doi:10.1234/two", "doi:10.1234/one")])
    assert import_reviews(store, path) == 2
    after = build_report(store)["compounds"][0]["counts"]
    assert after["confirmed_structural_dois"] == 2
    assert after["reviewed_samples"] == 1
    assert after["reviewed_replications"] == 1


def test_invalid_review_import_is_atomic(store):
    compound = add_records(store)
    path = review_csv(store, compound, [("doi:10.1234/one", ""), ("doi:10.1234/two", "doi:10.1234/missing")])
    with pytest.raises(ValueError):
        import_reviews(store, path)
    assert store.db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_review_cycles_rejected(store):
    compound = add_records(store)
    path = review_csv(store, compound, [("doi:10.1234/one", "doi:10.1234/two"), ("doi:10.1234/two", "doi:10.1234/one")])
    with pytest.raises(ValueError, match="Ciclo"):
        import_reviews(store, path)


def test_report_escapes_injected_title_and_csv_formulas(store):
    compound = add_records(store)
    job = store.add_job(compound["id"], "test", "html")
    store.page(job, [record("test", "html", title='<script>alert(1)</script> Phenazine perovskite')], None, 1, True)
    export_report(store)
    content = (store.directory / "report.html").read_text()
    assert "<script>alert(1)</script>" not in content
    csv_value = next(csv.DictReader(io.StringIO(csv_text([{"title": "=IMPORTXML()"}]).lstrip("\ufeff"))))
    assert csv_value["title"].startswith("'=")


def test_import_cif_and_text_idempotently(store, cif):
    text = store.directory / "article.txt"
    text.write_text("Phenazinium is an organic cation in the hybrid perovskite.\nReferences\nUnrelated article.")
    first = import_files(store, cif, text, "10.1234/test", "Synthetic import")
    second = import_files(store, cif, text, "10.1234/test", "Synthetic import")
    assert first == second
    assert store.db.execute("SELECT COUNT(*) FROM local_records").fetchone()[0] == 1
    report = export_report(store)
    assert report["compounds"][0]["counts"]["distinct_cif_files"] == 1
    assert "Unrelated article" not in report["compounds"][0]["works"][0]["records"][0]["fulltext"]
