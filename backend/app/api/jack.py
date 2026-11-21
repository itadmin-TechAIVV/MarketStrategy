"""Jack, the in-app guide: a short two-way chat per user, kept across sessions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..agent.jack import MAX_HISTORY, ask_jack, build_context
from ..agent.llm import LLMError
from ..auth import Tenant, get_tenant
from ..db import get_db, new_id, utcnow
from ..services.account import onboarding_state

router = APIRouter(prefix="/api/jack", tags=["jack"])
KEEP = 60  # messages kept per user


class PageIn(BaseModel):
    path: str = Field(default="/app", max_length=300)
    strategy_id: str | None = Field(default=None, max_length=64)


class JackIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    page: PageIn | None = None


def _public(m: dict) -> dict:
    return {
        "id": m["_id"],
        "role": m["role"],
        "text": m["text"],
        "suggestions": m.get("suggestions", []),
        "action": m.get("action", "none"),
        "strategy_id": m.get("strategy_id", ""),
        "action_label": m.get("action_label", ""),
        "created_at": m["created_at"],
    }


def _scope(tenant: Tenant) -> dict:
    return {"organization_id": tenant.organization_id, "user_id": tenant.user_id}


async def _history(tenant: Tenant, limit: int) -> list[dict]:
    cur = get_db().jack_messages.find(_scope(tenant)).sort("created_at", -1).limit(limit)
    return list(reversed([m async for m in cur]))


@router.get("/messages")
async def messages(tenant: Tenant = Depends(get_tenant)):
    return [_public(m) for m in await _history(tenant, KEEP)]


@router.delete("/messages", status_code=204)
async def clear(tenant: Tenant = Depends(get_tenant)):
    await get_db().jack_messages.delete_many(_scope(tenant))


@router.post("/messages")
async def ask(body: JackIn, tenant: Tenant = Depends(get_tenant)):
    db = get_db()
    user = await db.users.find_one({"_id": tenant.user_id, "organization_id": tenant.organization_id})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    org = await db.organizations.find_one({"_id": tenant.organization_id})

    workspaces = []
    async for w in db.workspaces.find({"organization_id": tenant.organization_id}).sort("updated_at", -1).limit(15):
        workspaces.append({
            "id": w["_id"],
            "product_name": w["product_name"],
            "current_stage": w.get("current_stage", "brief"),
            "busy": bool(w.get("turn_lock_until") and w["turn_lock_until"] > utcnow()),
            "pending_question": bool(w.get("pending_ask")),
            "crawl": w.get("crawl"),
        })
    page = None
    if body.page:
        page = {"path": body.page.path}
        match = next((w for w in workspaces if w["id"] == body.page.strategy_id), None)
        if match:
            page["strategy_name"] = match["product_name"]

    context = build_context(
        {"name": user["name"], "organization_name": (org or {}).get("name", "")},
        onboarding_state(user.get("first_login_at"), utcnow()),
        workspaces,
        page,
    )
    history = await _history(tenant, MAX_HISTORY)
    try:
        reply = await ask_jack(body.text.strip(), history, context, {w["id"] for w in workspaces})
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    now = utcnow()
    user_msg = {"_id": new_id(), **_scope(tenant), "role": "user", "text": body.text.strip(), "created_at": now}
    jack_msg = {
        "_id": new_id(), **_scope(tenant), "role": "jack", "text": reply["reply"],
        "suggestions": reply["suggestions"], "action": reply["action"], "strategy_id": reply["strategy_id"],
        "action_label": reply["action_label"], "created_at": utcnow(),
    }
    await db.jack_messages.insert_many([user_msg, jack_msg])

    # Keep the history bounded.
    old = db.jack_messages.find(_scope(tenant), {"_id": 1}).sort("created_at", -1).skip(KEEP)
    stale = [m["_id"] async for m in old]
    if stale:
        await db.jack_messages.delete_many({"_id": {"$in": stale}, **_scope(tenant)})

    return {"user": _public(user_msg), "jack": _public(jack_msg)}
