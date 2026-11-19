"""Workspaces (one per product), their sources, sections, transcript and export."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ..agent.stages import STAGES
from ..auth import Tenant, get_tenant
from ..crawler import UnsafeUrlError, normalize_start_url
from ..db import get_db, new_id, utcnow
from ..services.export import render_markdown
from ..services.sections import MongoSectionStore, SectionError, SectionService
from ..services.sources import active_sources, paste_doc, source_summary

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=120)
    website_url: str = Field(min_length=3, max_length=500)


class SectionEditIn(BaseModel):
    body_md: str = Field(min_length=1, max_length=20_000)


class PasteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100_000)


def public_workspace(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "product_name": doc["product_name"],
        "website_url": doc["website_url"],
        "current_stage": doc.get("current_stage", "brief"),
        "crawl": doc.get("crawl"),
        "pending_ask": (doc.get("pending_ask") or {}).get("ask"),
        "busy": bool(doc.get("turn_lock_until")),
        "created_at": doc["created_at"],
        "updated_at": doc.get("updated_at"),
    }


def public_section(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("organization_id",)} | {"id": doc["_id"]}


async def load_workspace(tenant: Tenant, workspace_id: str) -> dict:
    doc = await get_db().workspaces.find_one({"_id": workspace_id, "organization_id": tenant.organization_id})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return doc


def section_service(tenant: Tenant, workspace_id: str) -> SectionService:
    return SectionService(MongoSectionStore(get_db(), tenant.organization_id), tenant.organization_id, workspace_id)


@router.get("")
async def list_workspaces(tenant: Tenant = Depends(get_tenant)):
    cur = get_db().workspaces.find({"organization_id": tenant.organization_id}).sort("updated_at", -1)
    return [public_workspace(d) async for d in cur]


@router.post("", status_code=201)
async def create_workspace(body: WorkspaceIn, tenant: Tenant = Depends(get_tenant)):
    try:
        url = normalize_start_url(body.website_url)
    except UnsafeUrlError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    now = utcnow()
    doc = {
        "_id": new_id(),
        "organization_id": tenant.organization_id,
        "created_by": tenant.user_id,
        "product_name": body.product_name.strip(),
        "website_url": url,
        "current_stage": STAGES[0].key,
        "crawl": None,
        "pending_ask": None,
        "pending_notes": [],
        "turn_lock_until": None,
        "created_at": now,
        "updated_at": now,
    }
    await get_db().workspaces.insert_one(doc)
    return public_workspace(doc)


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str, tenant: Tenant = Depends(get_tenant)):
    ws = await load_workspace(tenant, workspace_id)
    svc = section_service(tenant, workspace_id)
    sections = await svc.store.list(workspace_id)
    statuses = await svc.stage_statuses()
    return {
        "workspace": public_workspace(ws),
        "stages": [
            {
                "key": st.key,
                "title": st.title,
                "ready": st.ready,
                "optional": st.optional,
                "status": statuses[st.key],
                "sections": [{"key": s.key, "title": s.title, "hint": s.hint} for s in st.sections],
            }
            for st in STAGES
        ],
        "sections": [public_section(d) for d in sections],
    }


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: str, tenant: Tenant = Depends(get_tenant)):
    await load_workspace(tenant, workspace_id)
    db = get_db()
    q = {"organization_id": tenant.organization_id, "workspace_id": workspace_id}
    for coll in (db.sources, db.messages, db.strategy_sections, db.section_versions):
        await coll.delete_many(q)
    await db.workspaces.delete_one({"_id": workspace_id, "organization_id": tenant.organization_id})
    return Response(status_code=204)


@router.get("/{workspace_id}/messages")
async def transcript(workspace_id: str, tenant: Tenant = Depends(get_tenant)):
    await load_workspace(tenant, workspace_id)
    cur = get_db().messages.find(
        {"organization_id": tenant.organization_id, "workspace_id": workspace_id, "role": {"$in": ["user", "assistant"]}},
        {"role": 1, "display": 1, "seq": 1, "created_at": 1},
    ).sort("seq", 1)
    items = []
    async for m in cur:
        for d in m.get("display") or []:
            items.append({"role": m["role"], **d, "seq": m["seq"]})
    return items


@router.get("/{workspace_id}/sources")
async def list_sources(workspace_id: str, tenant: Tenant = Depends(get_tenant)):
    await load_workspace(tenant, workspace_id)
    return [source_summary(s) for s in await active_sources(tenant.organization_id, workspace_id)]


@router.post("/{workspace_id}/sources", status_code=201)
async def add_context(workspace_id: str, body: PasteIn, tenant: Tenant = Depends(get_tenant)):
    """User pastes extra context (deck text, notes). The agent is told about it on its next turn."""
    await load_workspace(tenant, workspace_id)
    doc = paste_doc(tenant.organization_id, workspace_id, body.title.strip(), body.text)
    db = get_db()
    await db.sources.insert_one(doc)
    await db.workspaces.update_one(
        {"_id": workspace_id, "organization_id": tenant.organization_id},
        {"$push": {"pending_notes": f"The user added context '{doc['title']}' (source_id {doc['_id']}). Read it with read_sources and use it."}},
    )
    return source_summary(doc)


@router.patch("/{workspace_id}/sections/{key}")
async def edit_section(workspace_id: str, key: str, body: SectionEditIn, tenant: Tenant = Depends(get_tenant)):
    await load_workspace(tenant, workspace_id)
    svc = section_service(tenant, workspace_id)
    try:
        doc, flagged = await svc.edit_by_user(key, body.body_md)
    except SectionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    note = f"The user edited section {key} ('{doc['title']}') in the document. It is now confirmed as written."
    if flagged:
        note += f" These sections are now flagged needs_refresh: {', '.join(flagged)}."
    await get_db().workspaces.update_one(
        {"_id": workspace_id, "organization_id": tenant.organization_id},
        {"$push": {"pending_notes": note}, "$set": {"updated_at": utcnow()}},
    )
    return {"section": public_section(doc), "flagged": flagged}


@router.post("/{workspace_id}/sections/{key}/confirm")
async def confirm_section(workspace_id: str, key: str, tenant: Tenant = Depends(get_tenant)):
    await load_workspace(tenant, workspace_id)
    svc = section_service(tenant, workspace_id)
    try:
        doc = await svc.confirm(key)
    except SectionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await get_db().workspaces.update_one(
        {"_id": workspace_id, "organization_id": tenant.organization_id},
        {"$push": {"pending_notes": f"The user confirmed section {key} from the document."}},
    )
    return public_section(doc)


@router.get("/{workspace_id}/export.md")
async def export_markdown(workspace_id: str, tenant: Tenant = Depends(get_tenant)):
    ws = await load_workspace(tenant, workspace_id)
    svc = section_service(tenant, workspace_id)
    sections = await svc.store.list(workspace_id)
    sources = await active_sources(tenant.organization_id, workspace_id)
    md = render_markdown(ws, sections, sources, await svc.stage_statuses())
    filename = "".join(c if c.isalnum() else "-" for c in ws["product_name"]).strip("-").lower() or "strategy"
    return Response(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}-gtm-strategy.md"'},
    )
