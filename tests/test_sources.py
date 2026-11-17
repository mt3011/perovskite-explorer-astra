import pytest

from perovskite_explorer.http import SourceError, Unavailable
from perovskite_explorer.pipeline import DEFAULTS, fulltext
from perovskite_explorer.sources import fetch_page, parse_hybrid3, parse_openalex


class FakeHTTP:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def json(self, url, params=None):
        self.calls.append((url, params))
        return self.data


def test_crossref_cursor_and_truncation():
    http = FakeHTTP({"message": {"items": [{"DOI": "10.1234/x", "title": ["x"]}],
                                 "total-results": 9999, "next-cursor": "next"}})
    page = fetch_page("crossref", "query", "saved", 0, http, DEFAULTS | {"max_results": 1})
    assert http.calls[0][1]["cursor"] == "saved"
    assert page.done and page.truncated
    assert page.total == 9999
    assert len(page.records) == 1


def test_openalex_without_key_cannot_claim_pagination_complete(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    http = FakeHTTP({"meta": {"count": 5}, "results": [{"id": "W1", "title": "Title"}]})
    page = fetch_page("openalex", "query", None, 0, http, DEFAULTS | {"page_size": 1})
    assert not page.done
    with pytest.raises(Unavailable, match="OPENALEX_API_KEY"):
        fetch_page("openalex", "query", page.cursor, 1, http, DEFAULTS)


def test_openalex_key_passed_but_not_needed_for_offline_parsing(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "example-test-token")
    http = FakeHTTP({"meta": {"count": 1, "next_cursor": None}, "results": [{"id": "W1"}]})
    page = fetch_page("openalex", "query", None, 0, http, DEFAULTS)
    assert page.done and not page.truncated
    assert http.calls[0][1]["api_key"] == "example-test-token"


def test_openalex_reconstructs_abstract_positions():
    rec = parse_openalex({"id": "W1", "abstract_inverted_index": {"Phenazine": [0], "is": [1], "here": [2, 3]}})
    assert rec["abstract"] == "Phenazine is here here"


def test_europepmc_zero_is_success_not_unavailable():
    http = FakeHTTP({"hitCount": 0, "resultList": {"result": []}})
    page = fetch_page("europepmc", "q", None, 0, http, DEFAULTS)
    assert page.done and page.total == 0 and not page.truncated


def test_hybrid3_zero_dimensional_preserved():
    rec = parse_hybrid3({"pk": 1, "system": {"id": 2, "dimensionality": 0, "compound_name": "phenazinium"},
                        "is_experimental": False, "reference": {"doi_isbn": "10.1234/x"}})
    assert rec["structures"][0]["dimensionality"] == 0
    assert rec["type"] == "computed-dataset"
    assert rec["structures"][0]["url"] == ""


@pytest.mark.parametrize("raw,dimension", [(3, 2.5), (4, 3), (None, None)])
def test_hybrid3_raw_choice_is_not_physical_dimension(raw, dimension):
    rec = parse_hybrid3({"pk": 1, "system": {"dimensionality": raw}})
    assert rec["structures"][0]["dimensionality"] == dimension
    assert rec["metadata"]["system"]["dimensionality_source_code"] == raw


def test_hybrid3_cursor_cannot_change_domain():
    with pytest.raises(SourceError, match="domínio"):
        fetch_page("hybrid3", "all", "https://other.example/a", 0, FakeHTTP({}), DEFAULTS)


def test_hybrid3_smaller_page_preserves_checkpoint_offset():
    from urllib.parse import parse_qs, urlsplit
    http = FakeHTTP({"count": 301, "next": None, "results": [{"pk": 1}]})
    fetch_page("hybrid3", "all", "https://materials.hybrid3.duke.edu/materials/datasets/?page=7&page_size=50",
               300, http, DEFAULTS)
    params = parse_qs(urlsplit(http.calls[0][0]).query)
    assert params["page"] == ["13"]
    assert params["page_size"] == ["25"]


def test_fulltext_excludes_reference_list():
    class Fake:
        def get(self, url):
            return b'<article><body><sec><p>Control material was studied.</p></sec><ref-list><ref><p>Phenazine organic cation in perovskite.</p></ref></ref-list></body><back><ref-list><p>More references</p></ref-list></back></article>'
    data = fulltext("PMC123", Fake())
    assert "Phenazine" not in data["text"]
    assert "Control material" in data["text"]


def test_xml_entity_not_accepted():
    class Fake:
        def get(self, url):
            return b'<!DOCTYPE x [<!ENTITY y "value">]><article/>'
    with pytest.raises(SourceError, match="entidades"):
        fulltext("PMC1", Fake())


def test_cod_has_no_fictitious_offset():
    http = FakeHTTP([{"file": str(n)} for n in range(5)])
    page = fetch_page("cod", "phenazine", None, 0, http, DEFAULTS | {"max_results": 2})
    assert page.truncated and page.total == 5
    assert http.calls[0][1] == {"text": "phenazine", "format": "json"}


def test_csd_missing_is_explicit(tmp_path, monkeypatch):
    import sys
    from perovskite_explorer.sources import csd_search
    monkeypatch.setitem(sys.modules, "ccdc", None)
    with pytest.raises(Unavailable, match="SDK"):
        csd_search("phenazine", tmp_path, 10)
