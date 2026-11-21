"""Account rules (preferences, password policy, onboarding window), session revocation and Jack's reply parsing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.agent.jack import build_context, parse_reply
from app.auth import session_revoked
from app.services.account import (
    AccountError,
    ONBOARDING_DAYS,
    check_new_password,
    merge_preferences,
    onboarding_state,
    preferences_of,
)

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


def test_preferences_default_and_merge():
    prefs = preferences_of({})
    assert prefs == {"theme": "material", "jack_autostart": True}
    assert preferences_of({"preferences": {"theme": "warm", "junk": 1}}) == {"theme": "warm", "jack_autostart": True}
    assert merge_preferences(prefs, {"theme": "warm", "jack_autostart": False}) == {"theme": "warm", "jack_autostart": False}


@pytest.mark.parametrize("change", [{"theme": "neon"}, {"jack_autostart": "yes"}, {"colour": "red"}])
def test_preferences_reject_bad_values(change):
    with pytest.raises(AccountError):
        merge_preferences(preferences_of({}), change)


@pytest.mark.parametrize(
    "pw, msg",
    [
        ("short1", "at least"),
        ("onlyletters", "Mix"),
        ("12345678901", "Mix"),
        (" padded123 ", "space"),
        ("yudhveer2026", "email name"),
        ("OldPass123", "different"),
    ],
)
def test_password_policy_rejects(pw, msg):
    with pytest.raises(AccountError, match=msg):
        check_new_password(pw, email="yudhveer@example.com", current_password="OldPass123")


def test_password_policy_accepts_good_password():
    check_new_password("Market-2026!", email="yudhveer@example.com", current_password="OldPass123")


def test_onboarding_window():
    assert onboarding_state(None, T0)["active"] is True
    first = onboarding_state(T0, T0 + timedelta(hours=3))
    assert first["day"] == 1 and first["days_left"] == ONBOARDING_DAYS and first["active"]
    last = onboarding_state(T0, T0 + timedelta(days=9, hours=23))
    assert last["day"] == 10 and last["days_left"] == 1 and last["active"]
    over = onboarding_state(T0, T0 + timedelta(days=10, minutes=1))
    assert over["day"] == 11 and over["days_left"] == 0 and not over["active"]


def test_session_revoked_after_password_change():
    changed = T0.replace(microsecond=0)
    user = {"tokens_valid_after": changed}
    assert session_revoked(int(changed.timestamp()) - 1, user)
    assert not session_revoked(int(changed.timestamp()), user)  # the fresh token from the same second is kept
    assert not session_revoked(0, {})


def test_parse_reply_keeps_valid_action():
    raw = '{"reply": "Open it", "suggestions": ["a","b","c","d"], "action": "open_strategy", "strategy_id": "w1", "action_label": ""}'
    out = parse_reply(raw, {"w1"})
    assert out["action"] == "open_strategy" and out["strategy_id"] == "w1"
    assert out["action_label"] == "Open strategy"
    assert len(out["suggestions"]) == 3


def test_parse_reply_drops_unknown_strategy_and_action():
    assert parse_reply('{"reply": "x", "action": "open_strategy", "strategy_id": "nope"}', {"w1"})["action"] == "none"
    assert parse_reply('{"reply": "x", "action": "delete_everything"}', set())["action"] == "none"
    assert parse_reply("not json at all", set())["reply"] == "not json at all"
    assert parse_reply("", set())["reply"]


def test_context_lists_strategies_and_page():
    ctx = build_context(
        {"name": "Yudhveer Singh", "organization_name": "TechAivv"},
        {"day": 2, "total_days": 10, "active": True},
        [{"id": "w1", "product_name": "Acme", "current_stage": "icp", "busy": False, "pending_question": True, "crawl": {"status": "done"}}],
        {"path": "/app/w/w1", "strategy_name": "Acme"},
    )
    assert "Yudhveer" in ctx and "id=w1" in ctx and "waiting for the user's answer" in ctx and "Acme" in ctx
