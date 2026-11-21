"""Account rules that don't need a database: preferences, password policy, onboarding window.

Kept pure so they can be tested without Mongo, and so the API layer stays thin.
"""
from __future__ import annotations

import math
from datetime import datetime

THEMES = ("material", "warm")
ONBOARDING_DAYS = 10  # Jack greets a new user automatically for this many days after their first login

DEFAULT_PREFERENCES: dict = {
    "theme": "material",
    # Jack opens by itself after login while onboarding is active. The user can switch this off.
    "jack_autostart": True,
}

PASSWORD_MIN = 8
PASSWORD_MAX = 200


class AccountError(ValueError):
    """A request was rejected; the message is shown to the user as is."""


def preferences_of(user: dict) -> dict:
    """The user's stored preferences on top of the defaults (unknown keys dropped)."""
    stored = user.get("preferences") or {}
    return {k: stored.get(k, v) for k, v in DEFAULT_PREFERENCES.items()}


def merge_preferences(current: dict, changes: dict) -> dict:
    """Validate a partial update and return the full new preference set."""
    out = dict(current)
    for key, value in changes.items():
        if value is None:
            continue
        if key == "theme":
            if value not in THEMES:
                raise AccountError(f"Theme must be one of: {', '.join(THEMES)}")
            out["theme"] = value
        elif key == "jack_autostart":
            if not isinstance(value, bool):
                raise AccountError("jack_autostart must be true or false")
            out["jack_autostart"] = value
        else:
            raise AccountError(f"Unknown preference '{key}'")
    return out


def check_new_password(new_password: str, *, email: str = "", current_password: str = "") -> None:
    """Raise AccountError when the new password is too weak to accept."""
    pw = new_password or ""
    if len(pw) < PASSWORD_MIN:
        raise AccountError(f"Use at least {PASSWORD_MIN} characters")
    if len(pw) > PASSWORD_MAX:
        raise AccountError(f"Use at most {PASSWORD_MAX} characters")
    if pw.strip() != pw or not pw.strip():
        raise AccountError("The password can't start or end with a space")
    if current_password and pw == current_password:
        raise AccountError("The new password must be different from the current one")
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in pw.lower():
        raise AccountError("Don't include your email name in the password")
    if pw.isdigit() or pw.isalpha():
        raise AccountError("Mix letters with numbers or symbols")


def onboarding_state(first_login_at: datetime | None, now: datetime) -> dict:
    """Where the user is in the first-days window.

    day:       1 on the day of the first login, 2 the next day, ...
    days_left: days of onboarding remaining, including today (0 when over)
    active:    Jack should greet the user automatically
    """
    if first_login_at is None:
        return {"day": 1, "days_left": ONBOARDING_DAYS, "active": True, "total_days": ONBOARDING_DAYS}
    elapsed = (now - first_login_at).total_seconds() / 86_400
    day = max(1, math.floor(elapsed) + 1)
    days_left = max(0, ONBOARDING_DAYS - day + 1)
    return {"day": day, "days_left": days_left, "active": days_left > 0, "total_days": ONBOARDING_DAYS}
