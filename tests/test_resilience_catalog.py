"""The closed resilience set's catalog: its weights are the taxonomy's totals, and CATALOG.md is its data."""
import json
from pathlib import Path

from eval.resilience.closed.catalog_md import HERE, render

CATALOG = json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))
# Hammoudi (2016), Table 5.2: the totals of the categories kept in the catalog.
TOTALS = {"1.1.1.1": 56, "1.1.1.2": 57, "1.1.1.3": 54, "1.1.1.4": 60, "1.1.1.5": 55, "1.1.1.6": 45, "1.1.1.7": 52,
          "1.1.1.8": 48, "1.1.1.9": 47, "1.1.2": 63, "1.2.1": 131, "1.2.2": 116, "3.1": 17, "3.2": 21, "5.1": 29, "5.2": 24}


def test_every_kept_category_carries_its_total_and_its_operators_share_it():
    ops = [o for o in CATALOG["operators"] if o["source"] == "hammoudi2016"]
    assert {o["category"] for o in ops} == set(TOTALS)
    for category, total in TOTALS.items():
        mine = [o for o in ops if o["category"] == category]
        assert all(o["category_total"] == total for o in mine)
        assert sum(o["weight"] for o in mine) == total


def test_every_category_of_the_taxonomy_is_either_kept_or_left_out_with_a_reason():
    left = {x["category"] for x in CATALOG["left_out"]}
    assert left == {"2.1", "2.2", "2.3", "2.4", "4.1", "4.2"} and not left & set(TOTALS)
    assert all(x["why"] for x in CATALOG["left_out"])


def test_the_adversarial_level_names_its_source_categories():
    l5 = [o for o in CATALOG["operators"] if o["level"] == 5]
    assert {o["source"] for o in l5} == {"greshake2023", "gray2018"} and len(l5) == 4
    assert all("adaptation" in o["category"] for o in l5 if o["source"] == "gray2018")


def test_the_readable_catalog_is_exactly_its_data():
    assert (HERE / "CATALOG.md").read_text(encoding="utf-8") == render(CATALOG)
    assert CATALOG["seed"] == 20261024 and CATALOG["operators_per_task_and_level"] == 2


def test_every_injected_phrase_says_where_it_comes_from_and_how_it_was_adapted():
    inj = CATALOG["injected_phrases"]
    listings = {x["listing"] for x in inj["listings"]}
    assert listings == {"Prompt 4", "Prompt 8"}
    assert len(inj["phrases"]) == 6 and {p["kind"] for p in inj["phrases"]} == {"fraud", "intrusion"}
    for p in inj["phrases"]:
        assert p["listing"] in listings and p["source_location"] and p["translation_pt"] and p["fits"]
        assert p["adaptation"] and p["adapted_by"] == "Lucas dos Santos Dantas"   # never from scratch: the change is described


def test_the_catalog_is_ready_with_every_phrase_in_both_languages():
    from eval.resilience.closed.catalog_md import ready
    assert ready(CATALOG) and all(p["translation_pt"] and p["adapted_en"] for p in CATALOG["injected_phrases"]["phrases"])
    missing = {**CATALOG, "injected_phrases": {**CATALOG["injected_phrases"],
               "phrases": [{**p, "adapted_en": "PENDING: x"} for p in CATALOG["injected_phrases"]["phrases"]]}}
    assert not ready(missing)


def test_level_2_draws_among_all_senses_of_the_same_part_of_speech_with_at_most_3_redraws():
    rule = next(r for r in CATALOG["rules"] if r.startswith("Level 2's synonyms"))
    assert "all the senses" in rule and "same part of speech" in rule and "at most 3 times" in rule
    assert CATALOG["version"] == 2 and CATALOG["changes"] and "openwordnet_pt" not in CATALOG["sources"]
    assert {"paiva2012", "bond2013", "wordnet"} <= set(CATALOG["sources"])
