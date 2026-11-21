"""Account endpoints end to end over HTTP, against a small in-memory stand-in for MongoDB."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import account as account_api
from app.auth import hash_password
from app.main import app


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    @staticmethod
    def _match(doc: dict, flt: dict) -> bool:
        return all(doc.get(k) == v for k, v in flt.items())

    async def find_one(self, flt: dict, projection: dict | None = None):
        for d in self.docs:
            if self._match(d, flt):
                return dict(d)
        return None

    async def update_one(self, flt: dict, update: dict, upsert: bool = False):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return

    async def insert_one(self, doc: dict):
        self.docs.append(dict(doc))


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()
        self.organizations = FakeCollection()


@pytest.fixture
def client(monkeypatch):
    db = FakeDB()
    db.organizations.docs.append({"_id": "org1", "name": "TechAivv"})
    db.users.docs.append({
        "_id": "u1", "organization_id": "org1", "name": "Yudhveer Singh", "email": "yudhveer@example.com",
        "password_hash": hash_password("OldPass123"), "role": "admin",
    })
    monkeypatch.setattr(auth, "get_db", lambda: db)
    monkeypatch.setattr(account_api, "get_db", lambda: db)
    c = TestClient(app)  # not used as a context manager, so the lifespan (real Mongo indexes) doesn't run
    c.db = db
    return c


def login(client, password="OldPass123"):
    return client.post("/api/auth/login", json={"email": "yudhveer@example.com", "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_starts_onboarding_and_returns_preferences(client):
    res = login(client)
    assert res.status_code == 200
    user = res.json()["user"]
    assert user["onboarding"] == {"day": 1, "days_left": 10, "active": True, "total_days": 10}
    assert user["preferences"] == {"theme": "material", "jack_autostart": True}
    assert user["first_login_at"]


def test_profile_and_preferences(client):
    token = login(client).json()["token"]
    res = client.patch("/api/account/profile", json={"name": "Yudhveer S. Panwar", "organization_name": "TechAivv Labs"}, headers=bearer(token))
    assert res.status_code == 200
    assert res.json()["name"] == "Yudhveer S. Panwar"
    assert res.json()["organization"]["name"] == "TechAivv Labs"

    res = client.patch("/api/account/preferences", json={"theme": "warm", "jack_autostart": False}, headers=bearer(token))
    assert res.json() == {"theme": "warm", "jack_autostart": False}
    assert client.patch("/api/account/preferences", json={"theme": "neon"}, headers=bearer(token)).status_code == 422
    assert client.get("/api/auth/me", headers=bearer(token)).json()["preferences"]["theme"] == "warm"


def test_password_change_signs_out_other_sessions(client):
    old_token = login(client).json()["token"]
    time.sleep(1.1)  # token timestamps have one-second resolution

    wrong = client.post("/api/account/password", json={"current_password": "nope", "new_password": "Market-2026!"}, headers=bearer(old_token))
    assert wrong.status_code == 400
    weak = client.post("/api/account/password", json={"current_password": "OldPass123", "new_password": "short"}, headers=bearer(old_token))
    assert weak.status_code == 422

    res = client.post("/api/account/password", json={"current_password": "OldPass123", "new_password": "Market-2026!"}, headers=bearer(old_token))
    assert res.status_code == 200
    new_token = res.json()["token"]

    assert client.get("/api/auth/me", headers=bearer(new_token)).status_code == 200
    revoked = client.get("/api/auth/me", headers=bearer(old_token))
    assert revoked.status_code == 401 and "password was changed" in revoked.json()["detail"]

    assert login(client, "OldPass123").status_code == 401
    assert login(client, "Market-2026!").status_code == 200
