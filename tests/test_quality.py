import pytest

from perovskite_explorer.analysis import assess_work, deduplicate, evidence
from perovskite_explorer.identity import read_compounds, resolve
from perovskite_explorer.sources import record
from perovskite_explorer.structures import inspect_cif
from perovskite_explorer.util import mentions


@pytest.mark.parametrize("text,expected", [
    ("Phenazine is an additive for perovskite solar cells.", "nonstructural_use"),
    ("Phenazinium acts as an organic cation in the 1D hybrid lead iodide crystal.", "structural_candidate"),
    ("Phenazine was not incorporated into the perovskite lattice.", "mention_only"),
    ("Phenazine could be an organic cation in a hybrid perovskite.", "mention_only"),
    ("Phenazine is discussed in relation to perovskite materials.", "mention_only"),
    ("Phenazine has a biological role in bacteria.", "outside_scope"),
    ("Dipyrido-phenazine is an organic cation in a hybrid crystal.", "no_exact_mention"),
    ("Phenazine-based derivatives are hole transporting materials in perovskite devices.", "no_exact_mention"),
    ("Phenazinium is an organic cation in a hybrid perovskite and an additive in another phase.", "mixed_evidence"),
])
def test_false_positive_boundaries(compound, text, expected):
    result = evidence(record("test", "1", title=text), compound)
    assert result["status"] == expected
    assert result["status"] != "structural_confirmed"


def test_cif_presence_does_not_confirm_role(compound, cif):
    info = inspect_cif(cif)
    assert info["valid_structure"]
    assert info["blocks"][0]["hybrid_composition_candidate"]
    assert info["blocks"][0]["warnings"]
    rec = record("local", "x", kind="structure", metadata={"chemical_name": "Phenazinium lead iodide", "formula": "C12 H10 N2 Pb I4"})
    assert evidence(rec, compound)["status"] == "structural_candidate"
    rec["metadata"]["formula"] = "C12 H8 N2"
    assert evidence(rec, compound)["status"] == "outside_scope"


def test_missing_coordinates_not_a_structure(cif):
    cif.write_text("data_test\n_chemical_formula_sum 'C12 H8 N2'\n")
    assert not inspect_cif(cif)["valid_structure"]


def test_multi_block_and_missing_fractional_values(cif):
    original = cif.read_text()
    cif.write_text(original.replace("data_synthetic_test_only", "data_invalid").replace("0.1 0.2 0.3", "? 0.2 0.3") + original)
    info = inspect_cif(cif)
    assert not info["blocks"][0]["has_coordinates"]
    assert info["blocks"][1]["has_coordinates"]


def test_doi_dedup_not_title_dedup():
    records = [record("a", "1", title="Identical", doi="https://doi.org/10.1234/ABC"),
               record("b", "2", title="Identical", doi="10.1234/abc"),
               record("c", "3", title="Identical"), record("d", "4", title="Identical")]
    works = deduplicate(records + records)
    assert len(works) == 3
    assert len(next(w for w in works if w["doi"])["records"]) == 2


def test_ambiguous_name_does_not_call_pubchem(tmp_path):
    file = tmp_path / "input.txt"
    file.write_text("4-Aminophenyl sulfone\n")
    compound = read_compounds(file)[0]
    assert resolve(compound, None)["status"] == "ambiguous"


def test_multiple_cids_never_pick_first(compound):
    class Fake:
        def json(self, *args):
            return {"IdentifierList": {"CID": [1, 2]}}
    assert resolve(compound, Fake())["status"] == "ambiguous"


def test_review_and_retraction_do_not_count_primary(compound):
    rec = record("test", "1", title="Phenazinium organic cation in a hybrid perovskite.", type="review")
    assert evidence(rec, compound)["status"] == "review_context"
    rec["metadata"]["is_retracted"] = True
    assert evidence(rec, compound)["status"] == "publication_alert"


def test_property_not_attributed_from_other_sentence(compound):
    rec = record("test", "1", abstract="Phenazine was an additive in perovskite devices. The reference sample had a band gap of 1.5 eV.")
    assert not evidence(rec, compound)["properties_context"]


def test_cross_source_conflict_requires_review(compound):
    a = record("a", "1", doi="10.1234/x", title="Phenazinium organic cation in a hybrid perovskite crystal.")
    b = record("b", "2", doi="10.1234/x", title="Phenazine additive for perovskite films.")
    assert assess_work(deduplicate([a, b])[0], compound)["classification"] == "mixed_evidence"


def test_exact_word_matching():
    assert mentions("nicotinamide and niacinamide", ["nicotinic acid"]) == []
    assert mentions("3-aminobenzoic acid", ["aminobenzoic acid"]) == []
