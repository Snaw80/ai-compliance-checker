"""Applicability table + country profile table (tables/*.yaml). No database needed."""

import json
from datetime import date
from pathlib import Path

import pytest

from aiact.tables import (
    TableError,
    get_country_profile,
    load_countries,
    load_obligations,
    lookup_applicability,
)

TODAY = date(2026, 11, 19)
CHUNKS = Path("data/corpus/chunks.jsonl")


def ids(results):
    return [r.obligation.id for r in results]


# ---------------------------------------------------------------------------
# Applicability: dates come from Art. 113 / Art. 111 of the consolidated AI Act
# ---------------------------------------------------------------------------

def test_chatbot_disclosure_applies_since_august_2026():
    [r] = lookup_applicability(article="Art. 50(1)", on=TODAY)
    assert r.applies_from == date(2026, 8, 2)
    assert r.status == "applicable"
    assert r.days_until is None


def test_annex_iii_high_risk_postponed_by_omnibus():
    [r] = lookup_applicability(article="Annex III", on=TODAY)
    assert r.applies_from == date(2027, 12, 2)
    assert r.status == "not_yet_applicable"
    assert r.days_until == (date(2027, 12, 2) - TODAY).days


def test_annex_i_high_risk_applies_from_august_2028():
    [r] = lookup_applicability(article="Annex I", on=TODAY)
    assert r.applies_from == date(2028, 8, 2)


def test_status_flips_on_the_day_of_application():
    [before] = lookup_applicability(article="Art. 50(1)", on=date(2026, 8, 1))
    [on_day] = lookup_applicability(article="Art. 50(1)", on=date(2026, 8, 2))
    assert before.status == "not_yet_applicable" and before.days_until == 1
    assert on_day.status == "applicable"


def test_new_omnibus_prohibition_gets_its_own_date_not_the_art5_date():
    [r] = lookup_applicability(article="Art. 5(1)(ba)", on=TODAY)
    assert r.applies_from == date(2026, 12, 2)


def test_old_prohibition_applies_since_february_2025():
    [r] = lookup_applicability(article="Art. 5(1)(f)", on=TODAY)
    assert r.applies_from == date(2025, 2, 2)


def test_broad_article_returns_every_row_inside_it():
    results = lookup_applicability(article="Art. 5", on=TODAY)
    assert {r.applies_from for r in results} == {date(2025, 2, 2), date(2026, 12, 2)}


def test_deployer_obligations_depend_on_high_risk_route():
    results = lookup_applicability(article="Art. 26(1)", on=TODAY)
    assert {r.applies_from for r in results} == {date(2027, 12, 2), date(2028, 8, 2)}


@pytest.mark.parametrize("article,expected", [
    ("Art. 3(1)", date(2025, 2, 2)),
    ("Art. 4", date(2025, 2, 2)),
    ("Art. 30", date(2025, 8, 2)),       # Chapter III Section 4
    ("Art. 53(1)", date(2025, 8, 2)),    # Chapter V (GPAI)
    ("Art. 70(2)", date(2025, 8, 2)),    # Chapter VII
    ("Art. 78", date(2025, 8, 2)),
    ("Art. 99(1)", date(2025, 8, 2)),    # Chapter XII ...
    ("Art. 101", date(2026, 8, 2)),      # ... except Art. 101 (Commission fines on GPAI)
    ("Art. 57(1)", date(2026, 8, 2)),    # general date
    ("Art. 71", date(2026, 8, 2)),
    ("Art. 75a", date(2026, 8, 2)),
    ("Art. 105", date(2026, 7, 27)),     # Art. 102-110
])
def test_article_dates_follow_art_113(article, expected):
    [r] = lookup_applicability(article=article, on=TODAY)
    assert r.applies_from == expected


def test_every_ai_act_article_has_a_date():
    for n in range(1, 114):
        assert lookup_applicability(article=f"Art. {n}", on=TODAY), f"Art. {n}"


def test_non_ai_act_reference_is_rejected():
    with pytest.raises(TableError):
        lookup_applicability(article="Recital 132", on=TODAY)


def test_art_50_2_marking_has_grace_period_for_existing_systems():
    [r] = lookup_applicability(article="Art. 50(2)", on=TODAY)
    [t] = r.transitions
    assert t["deadline"] == date(2026, 12, 2)
    assert t["status"] == "running"
    [r_later] = lookup_applicability(article="Art. 50(2)", on=date(2026, 12, 2))
    assert r_later.transitions[0]["status"] == "ended"


def test_lookup_by_obligation_id():
    [r] = lookup_applicability("gpai-model-obligations", on=TODAY)
    assert r.applies_from == date(2025, 8, 2)
    assert r.transitions[0]["deadline"] == date(2027, 8, 2)


def test_unknown_obligation_id_raises():
    with pytest.raises(TableError, match="unknown obligation"):
        lookup_applicability("no-such-thing", on=TODAY)


def test_no_filter_returns_all_rows():
    assert len(lookup_applicability(on=TODAY)) == len(load_obligations())


def test_member_state_gets_the_eu_date():
    [eu] = lookup_applicability(article="Art. 50(1)", on=TODAY)
    [fr] = lookup_applicability(article="Art. 50(1)", country="France", on=TODAY)
    assert (fr.applies_from, fr.status, fr.country) == (eu.applies_from, eu.status, "FR")


def test_eea_country_is_not_bound_yet():
    [r] = lookup_applicability(article="Art. 50(1)", country="NO", on=TODAY)
    assert r.status == "not_binding"
    assert "EEA" in r.note


def test_result_serialises_to_json():
    [r] = lookup_applicability(article="Art. 50(2)", on=TODAY)
    d = json.loads(json.dumps(r.to_dict()))
    assert d["applies_from"] == "2026-08-02"
    assert d["transitions"][0]["deadline"] == "2026-12-02"


@pytest.mark.skipif(not CHUNKS.exists(), reason="run `python -m aiact.ingest` first")
def test_source_chunk_ids_exist_in_corpus():
    chunk_ids = {json.loads(line)["chunk_id"] for line in CHUNKS.open()}
    for o in load_obligations():
        missing = [c for c in o.source_chunk_ids if c not in chunk_ids]
        assert not missing, f"{o.id}: {missing}"


# ---------------------------------------------------------------------------
# Country profiles
# ---------------------------------------------------------------------------

def test_all_27_member_states_and_3_eea_countries():
    rows = load_countries()
    assert len([r for r in rows if r["membership"] == "EU"]) == 27
    assert {r["iso2"] for r in rows if r["membership"] == "EEA"} == {"NO", "IS", "LI"}
    assert len({r["iso2"] for r in rows}) == 30


def test_ai_act_binding_only_for_eu_members():
    for r in load_countries():
        assert r["ai_act_binding"] is (r["membership"] == "EU"), r["iso2"]


@pytest.mark.parametrize("query", ["FI", "fi", "Finland", " finland "])
def test_country_lookup_by_code_or_name(query):
    assert get_country_profile(query)["iso2"] == "FI"


def test_country_lookup_by_alias():
    assert get_country_profile("Czech Republic")["iso2"] == "CZ"
    assert get_country_profile("The Netherlands")["iso2"] == "NL"


def test_unknown_country_raises():
    with pytest.raises(TableError, match="not an EU/EEA country"):
        get_country_profile("Switzerland")


def test_finland_profile():
    fi = get_country_profile("FI")
    assert fi["single_point_of_contact"]["name"].startswith("Traficom")
    assert fi["national_law"]["status"] == "in_force"
    assert fi["national_law"]["in_force_from"] == date(2026, 1, 1)


def test_profile_is_a_copy():
    get_country_profile("FI")["iso2"] = "XX"
    assert get_country_profile("FI")["iso2"] == "FI"


def test_no_country_claims_deep_coverage_without_national_documents():
    # No national documents are indexed, so no country may claim deep coverage.
    assert {r["coverage_tier"] for r in load_countries()} == {"profile_only"}


def test_validator_rejects_row_without_last_verified(tmp_path):
    bad = tmp_path / "countries.yaml"
    bad.write_text(
        "sources: {}\n"
        "countries:\n"
        "  - {iso2: FI, name: Finland, membership: EU, ai_act_binding: true,\n"
        "     coverage_tier: profile_only, confidence: medium, sources: [],\n"
        "     national_law: {status: none}, market_surveillance_authorities: []}\n"
    )
    with pytest.raises(TableError, match="last_verified"):
        load_countries(bad)


def test_validator_rejects_bad_enum(tmp_path):
    bad = tmp_path / "applicability.yaml"
    bad.write_text(
        "obligations:\n"
        "  - {id: x, obligation: x, articles: [Art. 4], roles: [provider], applies_from: 2025-02-02,\n"
        "     basis: x, source_chunk_ids: [], transitions: [{applies_to: x, effect: x, deadline: soon}]}\n"
    )
    with pytest.raises(TableError, match="deadline"):
        load_obligations(bad)
