"""Strategy-section update logic.

Rules:
- The agent can only save sections that exist in the stage registry.
- A "website" claim must cite at least one source stored in this workspace.
- Claims the user made (provenance "user") are the source of truth: the agent
  may not drop or rewrite them silently. It must ask, then the user's answer is
  saved as a new user claim.
- Any change to a section's content marks every section in downstream stages
  "needs_refresh" (dependency graph in agent/stages.py).
- Agent saves are drafts. Only the user's confirmation (or a user edit) makes a
  section "confirmed".
"""
from __future__ import annotations

from typing import Iterable, Protocol

from ..agent.stages import SECTION_DEFS, STAGE_BY_KEY, STAGES, Stage, downstream_stages, stage_of
from ..db import new_id, utcnow

PROVENANCES = ("website", "user", "assumption")
CONFIDENCES = ("High", "Medium", "Low")
STATUSES = ("draft", "confirmed", "needs_refresh")


class SectionError(ValueError):
    """A save was rejected; the message is written for the agent/user to act on."""


class SectionStore(Protocol):
    async def get(self, workspace_id: str, key: str) -> dict | None: ...
    async def list(self, workspace_id: str) -> list[dict]: ...
    async def put(self, doc: dict) -> None: ...
    async def save_version(self, doc: dict) -> None: ...


# ------------------------------------------------------------------ helpers
def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def normalize_claims(raw: Iterable[dict] | None) -> list[dict]:
    claims = []
    for c in raw or []:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        claims.append(
            {
                "text": text,
                "provenance": c.get("provenance", "assumption"),
                "source_ids": list(dict.fromkeys(c.get("source_ids") or [])),
            }
        )
    return claims


def validate_claims(claims: list[dict], known_source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    for i, c in enumerate(claims):
        prov = c["provenance"]
        if prov not in PROVENANCES:
            errors.append(f"claim {i + 1}: provenance must be one of {PROVENANCES}, got '{prov}'")
            continue
        if prov == "website":
            if not c["source_ids"]:
                errors.append(f"claim {i + 1} ('{c['text'][:60]}') is marked website but cites no source_ids")
            unknown = [s for s in c["source_ids"] if s not in known_source_ids]
            if unknown:
                errors.append(f"claim {i + 1} cites unknown source_ids {unknown}; use ids returned by crawl/read tools")
    return errors


def content_changed(old: dict | None, new: dict) -> bool:
    if old is None:
        return True
    if _norm(old.get("body_md", "")) != _norm(new.get("body_md", "")):
        return True
    old_claims = [(_norm(c["text"]), c["provenance"], tuple(c["source_ids"])) for c in old.get("claims", [])]
    new_claims = [(_norm(c["text"]), c["provenance"], tuple(c["source_ids"])) for c in new.get("claims", [])]
    return old_claims != new_claims


def stage_status(stage: Stage, sections_by_key: dict[str, dict]) -> str:
    docs = [sections_by_key[s.key] for s in stage.sections if s.key in sections_by_key]
    if not docs:
        return "not_started"
    if any(d["status"] == "needs_refresh" for d in docs):
        return "needs_refresh"
    if len(docs) == len(stage.sections) and all(d["status"] == "confirmed" for d in docs):
        return "confirmed"
    return "in_progress"


def build_agent_save(
    existing: dict | None,
    *,
    organization_id: str,
    workspace_id: str,
    key: str,
    body_md: str,
    claims: list[dict] | None,
    confidence: str,
    known_source_ids: set[str],
) -> dict:
    """Pure function: validate an agent save and return the new section document."""
    if key not in SECTION_DEFS:
        raise SectionError(f"Unknown section key '{key}'. Valid keys: {', '.join(SECTION_DEFS)}")
    stage, sdef = SECTION_DEFS[key]
    if not STAGE_BY_KEY[stage.key].ready:
        raise SectionError(f"Stage '{stage.key}' is not available yet in this version")
    if confidence not in CONFIDENCES:
        raise SectionError(f"confidence must be one of {CONFIDENCES}")
    if not (body_md or "").strip():
        raise SectionError("body_md is empty; write the section content in markdown")

    new_claims = normalize_claims(claims)
    errors = validate_claims(new_claims, known_source_ids)
    if errors:
        raise SectionError("Section not saved: " + "; ".join(errors))

    if existing:
        kept = {_norm(c["text"]) for c in new_claims if c["provenance"] == "user"}
        dropped = [c["text"] for c in existing.get("claims", []) if c["provenance"] == "user" and _norm(c["text"]) not in kept]
        if dropped:
            raise SectionError(
                "Section not saved: it drops claims the user stated, which override the website: "
                + " | ".join(dropped)
                + ". Keep them verbatim as provenance 'user', or ask the user before changing them."
            )

    now = utcnow()
    doc = {
        "_id": existing["_id"] if existing else new_id(),
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "key": key,
        "stage": stage.key,
        "title": sdef.title,
        "body_md": body_md.strip(),
        "claims": new_claims,
        "confidence": confidence,
        "status": "draft",
        "version": (existing["version"] + 1) if existing else 1,
        "updated_by": "agent",
        "user_edited": bool(existing and existing.get("user_edited")),
        "refresh_reason": None,
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
    }
    return doc


def build_user_edit(existing: dict, body_md: str) -> dict:
    if not (body_md or "").strip():
        raise SectionError("The section can't be empty")
    now = utcnow()
    doc = dict(existing)
    doc.update(
        body_md=body_md.strip(),
        status="confirmed",
        version=existing["version"] + 1,
        updated_by="user",
        user_edited=True,
        confidence="High",
        refresh_reason=None,
        updated_at=now,
    )
    # The edited text is the user's word: record it as a user claim so the agent must keep it.
    doc["claims"] = [c for c in existing.get("claims", []) if c["provenance"] != "user"] + [
        {"text": f"User-edited section text: {body_md.strip()}", "provenance": "user", "source_ids": []}
    ]
    return doc


# ------------------------------------------------------------------ service
class SectionService:
    def __init__(self, store: SectionStore, organization_id: str, workspace_id: str):
        self.store = store
        self.org = organization_id
        self.ws = workspace_id

    async def _flag_downstream(self, section_key: str, reason: str) -> list[str]:
        stage_key = stage_of(section_key)
        targets = set(downstream_stages(stage_key))
        flagged: list[str] = []
        if not targets:
            return flagged
        for doc in await self.store.list(self.ws):
            if doc["stage"] in targets and doc["status"] != "needs_refresh":
                doc = dict(doc, status="needs_refresh", refresh_reason=reason, updated_at=utcnow())
                await self.store.put(doc)
                flagged.append(doc["key"])
        return flagged

    async def _write(self, old: dict | None, new: dict, changed: bool) -> list[str]:
        if old is not None:
            await self.store.save_version(old)
        await self.store.put(new)
        if changed and old is not None:
            return await self._flag_downstream(new["key"], f"'{new['title']}' changed")
        return []

    async def save_from_agent(
        self, key: str, body_md: str, claims: list[dict] | None, confidence: str, known_source_ids: set[str]
    ) -> tuple[dict, list[str]]:
        existing = await self.store.get(self.ws, key)
        new = build_agent_save(
            existing,
            organization_id=self.org,
            workspace_id=self.ws,
            key=key,
            body_md=body_md,
            claims=claims,
            confidence=confidence,
            known_source_ids=known_source_ids,
        )
        changed = content_changed(existing, new)
        if existing and not changed and existing["status"] == "confirmed":
            return existing, []  # nothing new; keep the confirmation
        flagged = await self._write(existing, new, changed)
        return new, flagged

    async def edit_by_user(self, key: str, body_md: str) -> tuple[dict, list[str]]:
        existing = await self.store.get(self.ws, key)
        if not existing:
            raise SectionError(f"Section '{key}' does not exist yet")
        new = build_user_edit(existing, body_md)
        flagged = await self._write(existing, new, content_changed(existing, new))
        return new, flagged

    async def confirm(self, key: str) -> dict:
        existing = await self.store.get(self.ws, key)
        if not existing:
            raise SectionError(f"Section '{key}' has not been written yet, so it can't be confirmed")
        doc = dict(existing, status="confirmed", refresh_reason=None, updated_at=utcnow())
        await self.store.put(doc)
        return doc

    async def stage_statuses(self) -> dict[str, str]:
        by_key = {d["key"]: d for d in await self.store.list(self.ws)}
        return {st.key: stage_status(st, by_key) for st in STAGES}


class MemorySectionStore:
    """In-memory store (tests, and a reference for the Mongo implementation)."""

    def __init__(self):
        self.docs: dict[tuple[str, str], dict] = {}
        self.versions: list[dict] = []

    async def get(self, workspace_id: str, key: str) -> dict | None:
        doc = self.docs.get((workspace_id, key))
        return dict(doc) if doc else None

    async def list(self, workspace_id: str) -> list[dict]:
        return [dict(d) for (ws, _), d in self.docs.items() if ws == workspace_id]

    async def put(self, doc: dict) -> None:
        self.docs[(doc["workspace_id"], doc["key"])] = dict(doc)

    async def save_version(self, doc: dict) -> None:
        self.versions.append(dict(doc))


class MongoSectionStore:
    def __init__(self, db, organization_id: str):
        self.db = db
        self.org = organization_id

    async def get(self, workspace_id: str, key: str) -> dict | None:
        return await self.db.strategy_sections.find_one(
            {"organization_id": self.org, "workspace_id": workspace_id, "key": key}
        )

    async def list(self, workspace_id: str) -> list[dict]:
        cur = self.db.strategy_sections.find({"organization_id": self.org, "workspace_id": workspace_id})
        return [d async for d in cur]

    async def put(self, doc: dict) -> None:
        assert doc["organization_id"] == self.org
        await self.db.strategy_sections.replace_one({"_id": doc["_id"], "organization_id": self.org}, doc, upsert=True)

    async def save_version(self, doc: dict) -> None:
        snap = {k: v for k, v in doc.items() if k != "_id"}
        snap.update(_id=new_id(), section_id=doc["_id"], archived_at=utcnow())
        await self.db.section_versions.insert_one(snap)
