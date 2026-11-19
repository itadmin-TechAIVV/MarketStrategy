"""Section-update logic: validation, user-claim protection, confirmations, needs-refresh spread."""
from __future__ import annotations

import pytest

from app.agent.stages import STAGES, downstream_stages
from app.services.sections import MemorySectionStore, SectionError, SectionService

WS = "ws1"
ORG = "org1"
SOURCES = {"src_home", "src_pricing"}


@pytest.fixture
def svc():
    return SectionService(MemorySectionStore(), ORG, WS)


def web(text, *ids):
    return {"text": text, "provenance": "website", "source_ids": list(ids) or ["src_home"]}


async def test_agent_save_creates_draft(svc):
    doc, flagged = await svc.save_from_agent("brief.pricing", "Per seat, $20/mo", [web("$20 per seat", "src_pricing")], "High", SOURCES)
    assert doc["status"] == "draft"
    assert doc["version"] == 1
    assert doc["stage"] == "brief"
    assert doc["organization_id"] == ORG
    assert flagged == []


async def test_website_claim_needs_a_known_source(svc):
    with pytest.raises(SectionError, match="cites no source_ids"):
        await svc.save_from_agent("brief.pricing", "x", [{"text": "Free plan", "provenance": "website"}], "High", SOURCES)
    with pytest.raises(SectionError, match="unknown source_ids"):
        await svc.save_from_agent("brief.pricing", "x", [web("Free plan", "made_up")], "High", SOURCES)


async def test_assumptions_do_not_need_sources(svc):
    doc, _ = await svc.save_from_agent(
        "brief.gaps", "No pricing published", [{"text": "Likely enterprise sales-led", "provenance": "assumption"}], "Low", SOURCES
    )
    assert doc["claims"][0]["provenance"] == "assumption"


@pytest.mark.parametrize(
    "key, confidence, body, match",
    [
        ("brief.nope", "High", "x", "Unknown section key"),
        ("brief.pricing", "Very high", "x", "confidence"),
        ("brief.pricing", "High", "   ", "empty"),
        ("personas.list", "High", "x", "not available yet"),
    ],
)
async def test_invalid_saves_are_rejected(svc, key, confidence, body, match):
    with pytest.raises(SectionError, match=match):
        await svc.save_from_agent(key, body, [], confidence, SOURCES)


async def test_user_claims_cannot_be_dropped_by_agent(svc):
    await svc.save_from_agent(
        "brief.audience", "Mid-market", [{"text": "We only sell to banks", "provenance": "user"}], "High", SOURCES
    )
    with pytest.raises(SectionError, match="drops claims the user stated"):
        await svc.save_from_agent("brief.audience", "SMBs", [web("SMB focus")], "Medium", SOURCES)
    # Keeping the user claim (whitespace/case-insensitive) is fine.
    doc, _ = await svc.save_from_agent(
        "brief.audience",
        "Banks, mid-market",
        [{"text": "we only sell to  banks", "provenance": "user"}, web("Mid-market logos")],
        "High",
        SOURCES,
    )
    assert doc["version"] == 2


async def test_confirm_and_resave_without_change_keeps_confirmation(svc):
    await svc.save_from_agent("brief.pricing", "Per seat", [web("Per seat", "src_pricing")], "High", SOURCES)
    confirmed = await svc.confirm("brief.pricing")
    assert confirmed["status"] == "confirmed"
    doc, _ = await svc.save_from_agent("brief.pricing", "Per  seat", [web("per seat", "src_pricing")], "High", SOURCES)
    assert doc["status"] == "confirmed" and doc["version"] == 1


async def test_changing_a_confirmed_section_makes_it_draft_again(svc):
    await svc.save_from_agent("brief.pricing", "Per seat", [web("Per seat", "src_pricing")], "High", SOURCES)
    await svc.confirm("brief.pricing")
    doc, _ = await svc.save_from_agent("brief.pricing", "Usage based", [web("Usage based", "src_pricing")], "High", SOURCES)
    assert doc["status"] == "draft" and doc["version"] == 2
    assert len(svc.store.versions) == 1  # previous version archived


async def test_confirm_missing_section_fails(svc):
    with pytest.raises(SectionError):
        await svc.confirm("brief.product")


async def _fill_brief_and_icp(svc):
    for st in STAGES[:2]:
        for sec in st.sections:
            await svc.save_from_agent(sec.key, f"{sec.title} content", [web("x")], "Medium", SOURCES)
            await svc.confirm(sec.key)


async def test_editing_brief_flags_icp_needs_refresh(svc):
    await _fill_brief_and_icp(svc)
    statuses = await svc.stage_statuses()
    assert statuses["brief"] == "confirmed" and statuses["icp"] == "confirmed"

    doc, flagged = await svc.edit_by_user("brief.audience", "Only regional banks with 200-2000 staff")
    assert doc["status"] == "confirmed" and doc["updated_by"] == "user" and doc["user_edited"]
    assert any(c["provenance"] == "user" for c in doc["claims"])
    assert sorted(flagged) == sorted(s.key for s in STAGES[1].sections)

    statuses = await svc.stage_statuses()
    assert statuses["brief"] == "confirmed"
    assert statuses["icp"] == "needs_refresh"
    icp = await svc.store.get(WS, "icp.firmographics")
    assert "Who it seems built for" in icp["refresh_reason"]


async def test_editing_icp_does_not_flag_brief(svc):
    await _fill_brief_and_icp(svc)
    _, flagged = await svc.edit_by_user("icp.triggers", "New compliance rules")
    assert flagged == []
    assert (await svc.stage_statuses())["brief"] == "confirmed"


async def test_reconfirming_clears_needs_refresh(svc):
    await _fill_brief_and_icp(svc)
    await svc.edit_by_user("brief.product", "A new one-liner")
    for sec in STAGES[1].sections:
        await svc.confirm(sec.key)
    assert (await svc.stage_statuses())["icp"] == "confirmed"


async def test_user_edit_then_agent_must_keep_it(svc):
    await svc.save_from_agent("brief.product", "Old", [web("old")], "Medium", SOURCES)
    await svc.edit_by_user("brief.product", "Payroll for nurses")
    with pytest.raises(SectionError, match="drops claims the user stated"):
        await svc.save_from_agent("brief.product", "Something else", [web("x")], "High", SOURCES)


def test_dependency_graph_is_transitive():
    down = downstream_stages("brief")
    assert down[0] == "icp"
    assert "plan" in down and "messaging" in down
    assert downstream_stages("plan") == []
    assert "brief" not in downstream_stages("icp")
    assert set(downstream_stages("personas")) >= {"value", "difficulty", "channels", "messaging", "plan", "pricing"}


async def test_stage_status_in_progress_and_not_started(svc):
    await svc.save_from_agent("brief.product", "x", [web("x")], "High", SOURCES)
    statuses = await svc.stage_statuses()
    assert statuses["brief"] == "in_progress"
    assert statuses["icp"] == "not_started"
