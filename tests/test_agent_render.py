"""Citation check + rendering (no model, no database)."""

from datetime import date

from aiact.agent.evidence import compact_articles, country_text
from aiact.agent.llm import _destringify
from aiact.agent.render import DISCLAIMER, country_section, dates_in, render, split_tags, verify, when_section
from aiact.agent.schemas import Answer, Source
from aiact.tables import get_country_profile, lookup_applicability

SOURCES = [
    Source(tag="S1", kind="chunk", label="AI Act, Art. 50(1)", url="https://x/art50",
           text="Providers shall ensure that AI systems intended to interact directly with natural persons ...",
           refs=["Art. 50(1)"], chunk_ids=["eu-ai-act-consolidated:art_50:1"]),
    Source(tag="T1", kind="table", label="AI Act, Art. 113 (dates of application)",
           text="Applies from 2 August 2026. Status on 2026-11-19: applicable.", refs=["Art. 113"]),
]


def test_split_tags():
    assert split_tags("Tell users it is AI [S1][T1].") == ("Tell users it is AI.", ["S1", "T1"])
    assert split_tags("Both [S1, T1; FI]") == ("Both", ["S1", "T1", "FI"])
    assert split_tags("No tags here") == ("No tags here", [])


def test_verify_drops_invented_tags_and_counts_unsupported():
    a = Answer(summary="Yes.", points=["Tell users [S1][S9]", "Applies from 2 August 2026 [T1]", "Trust me"])
    points, v = verify(a, SOURCES)
    assert [p.sources for p in points] == [["S1"], ["T1"], []]
    assert v.n_points == 3 and v.unsupported == 1 and v.unknown_tags == ["S9"]
    assert v.unverified_dates == []


def test_verify_flags_dates_not_in_sources():
    a = Answer(summary="It applied from 2 August 2025.", points=["Since August 2026 [T1]", "From 2026-08-02 [T1]"])
    _, v = verify(a, SOURCES)
    assert v.unverified_dates == ["2 August 2025"]


def test_dates_in_formats():
    assert set(dates_in("2 Aug 2026, December 2, 2027, 2028-08-02 and August 2026")) == {
        (2026, 8, 2), (2027, 12, 2), (2028, 8, 2), (2026, 8, None)}


def test_render_numbers_sources_in_citation_order():
    a = Answer(summary="Yes [S1].", risk_tier="transparency",
               points=["Dates [T1]", "Tell users [S1]", "Unsourced"], caveats=["Check the guidelines [S1]."])
    points, v = verify(a, SOURCES)
    md, cited = render(a, points, SOURCES, v, sections=["**When**\nrow [T1][XX]"], caveats=["Assumed provider."])
    assert [s.tag for s in cited] == ["T1", "S1"]
    assert "row [1][XX]" in md  # section tags become footnotes too; unknown ones stay as text
    assert "- Dates [1]" in md and "- Tell users [2]" in md and "_(no source found)_" in md
    assert md.startswith("Yes.") and "limited risk" in md
    assert md.index("**When**") < md.index("**Caveats**") < md.index("**Sources**")
    assert "- Assumed provider.\n- Check the guidelines." in md and "[S1]" not in md
    assert "2. [AI Act, Art. 50(1)](https://x/art50)" in md and md.endswith(DISCLAIMER)


def test_destringify_repairs_qwen_tool_args():
    broken = '[{"text": "a", "n": [1]}], {"text": "b", "n": [2]}]'
    assert _destringify({"points": broken, "s": "[not json"}) == {
        "points": [{"text": "a", "n": [1]}, {"text": "b", "n": [2]}], "s": "[not json"}
    assert _destringify({"points": '["x [S1]", "y [T1]"]'}) == {"points": ["x [S1]", "y [T1]"]}


def test_compact_articles():
    assert compact_articles(("Art. 6", "Art. 7", "Art. 8", "Art. 50(1)", "Art. 51", "Annex III")) == \
        "Art. 6-8, Art. 50(1), Art. 51, Annex III"


def test_when_section_dates_and_grace_period():
    on = date(2026, 11, 19)
    rows = lookup_applicability("art50-content-marking", on=on) + lookup_applicability("high-risk-annex-iii", on=on)
    md = when_section(rows, {"art50-content-marking": "T1", "high-risk-annex-iii": "T2"},
                      {"art50-content-marking": "you generate images"})
    assert "| you generate images | 2 Aug 2026 | applies |" in md
    assert "(Art. 6-27, Annex III) [T2] | provider, deployer" in md and "| 2 Dec 2027 | not yet (in 378 days) |" in md
    assert "Deadline: 2 December 2026 [T1]" in md
    assert "2030" not in md  # transitions of rows that don't apply yet are left out


def test_country_section_and_text():
    md = country_section(["FI", "NO"])
    assert "- **Finland**: AI Act applies directly. National AI law: in force: Act on the Supervision" in md
    assert "Traficom is not the authority for every question" in md and md.rstrip().endswith("[NO]")
    assert "AI Act not binding yet (EEA)" in md and "Nkom) (proposed)" in md
    text = country_text(get_country_profile("NO"))
    assert "not binding here until it is incorporated into the EEA Agreement" in text and ".." not in text
