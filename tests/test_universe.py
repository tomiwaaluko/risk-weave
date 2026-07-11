import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "data" / "universe" / "entities.json"
SELECTION_PATH = ROOT / "data" / "universe" / "SELECTION.md"


SEC_TYPES = {
    "bank",
    "reit",
    "property_company",
    "cre_connected_company",
    "energy_company",
    "transport_company",
}


def load_universe():
    return json.loads(UNIVERSE_PATH.read_text())


def test_universe_size_and_unique_ids():
    universe = load_universe()
    entities = universe["entities"]
    assert universe["schema_version"] == "riskweave.entity_universe.v1"
    assert 100 <= len(entities) <= 200

    ids = [entity["id"] for entity in entities]
    assert len(ids) == len(set(ids))


def test_minimum_composition_for_cre_and_oil_packs():
    entities = load_universe()["entities"]
    counts = Counter(entity["entity_type"] for entity in entities)

    assert counts["bank"] >= 10
    assert counts["reit"] + counts["property_company"] >= 10
    assert counts["cre_connected_company"] >= 10
    assert counts["energy_company"] >= 10
    assert counts["transport_company"] >= 10
    assert counts["macro_factor"] >= 6
    assert counts["commodity"] >= 2

    assert sum("cre" in entity["packs"] for entity in entities) >= 40
    assert sum("oil" in entity["packs"] for entity in entities) >= 35


def test_sec_reporting_entities_have_resolvable_identifiers():
    entities = load_universe()["entities"]
    tickers = []
    ciks = []
    for entity in entities:
        if entity["entity_type"] not in SEC_TYPES:
            assert entity["ticker"] is None
            assert entity["cik"] is None
            continue

        tickers.append(entity["ticker"])
        ciks.append(entity["cik"])
        assert entity["ticker"]
        assert re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", entity["ticker"])
        assert re.fullmatch(r"\d{10}", entity["cik"])
        assert entity["sec_company_name"]
        assert entity["expected_reporting_periods"] >= 3
        assert entity["verification"]["ticker_cik_source"] == "SEC company_tickers.json"

    assert len(tickers) == len(set(tickers))
    assert len(ciks) == len(set(ciks))


def test_breach_distance_candidate_count_is_scoped():
    entities = load_universe()["entities"]
    candidates = [entity for entity in entities if entity["breach_distance_candidate"]]

    assert 10 <= len(candidates) <= 20
    assert all(entity["entity_type"] == "bank" for entity in candidates)


def test_selection_document_records_scope_guard_and_requirements():
    text = SELECTION_PATH.read_text()
    normalized = " ".join(text.split())

    assert "RW-SCOPE-001" in text
    assert "RW-FR-010" in text
    assert "RW-DATA-001" in text
    assert "does not imply wrongdoing" in normalized
    assert "not a claim that an entity is distressed" in normalized


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("universe validation passed")
