"""Agent tools: schemas sent to Claude and the server-side handlers that run them.

Inputs stream eagerly, so the server does not validate them; every input is
validated here with Pydantic before a handler runs.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field, ValidationError

from ..crawler import Crawler, FetchError, UnsafeUrlError, fetch_single_page
from ..db import get_db, new_id, utcnow
from ..services.sections import MongoSectionStore, SectionError, SectionService, stage_status
from ..services.sources import (
    active_sources,
    crawl_config,
    known_source_ids,
    page_to_doc,
    source_summary,
)
from .stages import STAGE_BY_KEY, STAGES, next_stage

Emit = Callable[[dict], Awaitable[None]]
log = logging.getLogger(__name__)

MAX_CHARS_PER_SOURCE = 12_000
MAX_CHARS_TOTAL = 80_000


@dataclass
class ToolContext:
    organization_id: str
    workspace: dict
    emit: Emit

    @property
    def workspace_id(self) -> str:
        return self.workspace["_id"]

    def sections(self) -> SectionService:
        return SectionService(MongoSectionStore(get_db(), self.organization_id), self.organization_id, self.workspace_id)


class ToolFailure(Exception):
    """Raised by a handler; returned to Claude as an is_error tool_result."""


# ------------------------------------------------------------------ inputs
class CrawlSiteIn(BaseModel):
    url: str | None = None
    force: bool = False


class FetchPageIn(BaseModel):
    url: str
    purpose: str = ""


class ReadSourcesIn(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    page_types: list[str] = Field(default_factory=list)


class ClaimIn(BaseModel):
    text: str
    provenance: Literal["website", "user", "assumption"]
    source_ids: list[str] = Field(default_factory=list)


class SaveSectionIn(BaseModel):
    key: str
    body_md: str
    claims: list[ClaimIn] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"]


class QuestionIn(BaseModel):
    id: str
    text: str
    options: list[str] = Field(default_factory=list, max_length=6)
    allow_free_text: bool = True
    multi_select: bool = False


class AskUserIn(BaseModel):
    intro: str = ""
    questions: list[QuestionIn] = Field(min_length=1, max_length=6)
    section_key: str | None = None


class UpdateStrategyIn(BaseModel):
    action: Literal["confirm_section", "complete_stage", "set_stage"]
    section_key: str | None = None
    stage: str | None = None


# ------------------------------------------------------------------ schemas
def _tool(name: str, description: str, schema: dict) -> dict:
    return {"name": name, "description": description, "input_schema": schema, "eager_input_streaming": True}


CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "provenance": {"type": "string", "enum": ["website", "user", "assumption"]},
        "source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "provenance"],
}

TOOLS: list[dict] = [
    _tool(
        "crawl_site",
        "Crawl the workspace's product website (home page + up to ~25 priority internal pages: pricing, product, "
        "features, solutions, use cases, customers, about, blog). Respects robots.txt. Stores each page as a source "
        "and returns the list of sources (source_id, url, title, page_type). If pages are already stored it returns "
        "them without re-crawling unless force=true.",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Override URL; defaults to the workspace website."},
                "force": {"type": "boolean", "description": "Re-crawl even if pages are stored."},
            },
        },
    ),
    _tool(
        "fetch_page",
        "Fetch one web page (for example a competitor's site or a page the crawl missed), store it as a source, "
        "and return its text.",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}, "purpose": {"type": "string"}},
            "required": ["url"],
        },
    ),
    _tool(
        "read_sources",
        "Read the text of stored sources (crawled pages, fetched pages, user-pasted context) by source_id and/or "
        "page_type (home, pricing, product, features, solutions, use_cases, customers, about, compare, blog, docs, "
        "security, other, user_context). With no filters, returns the list of sources without text.",
        {
            "type": "object",
            "properties": {
                "source_ids": {"type": "array", "items": {"type": "string"}},
                "page_types": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    _tool(
        "save_section",
        "Create or update one section of the strategy document. Saved as a draft. Website claims must cite "
        "source_ids. Claims with provenance 'user' that already exist must be kept verbatim.",
        {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Section key, e.g. brief.pricing or icp.triggers"},
                "body_md": {"type": "string", "description": "Section content in concise markdown."},
                "claims": {"type": "array", "items": CLAIM_SCHEMA},
                "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
            },
            "required": ["key", "body_md", "claims", "confidence"],
        },
    ),
    _tool(
        "ask_user",
        "Ask the user 1-6 short questions, each with multiple-choice options (suggested default first) and "
        "optional free text. This ends your turn; the answers come back as this tool's result.",
        {
            "type": "object",
            "properties": {
                "intro": {"type": "string", "description": "One or two sentences of context shown above the questions."},
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"}},
                            "allow_free_text": {"type": "boolean"},
                            "multi_select": {"type": "boolean"},
                        },
                        "required": ["id", "text", "options"],
                    },
                },
                "section_key": {"type": "string", "description": "The section this question confirms, if any."},
            },
            "required": ["questions"],
        },
    ),
    _tool(
        "update_strategy",
        "Change strategy state: confirm_section (after the user approved it), complete_stage (when all of a "
        "stage's sections are confirmed; moves to the next stage), or set_stage (jump to a stage the user asked for).",
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["confirm_section", "complete_stage", "set_stage"]},
                "section_key": {"type": "string"},
                "stage": {"type": "string"},
            },
            "required": ["action"],
        },
    ),
]

TOOL_INPUTS: dict[str, type[BaseModel]] = {
    "crawl_site": CrawlSiteIn,
    "fetch_page": FetchPageIn,
    "read_sources": ReadSourcesIn,
    "save_section": SaveSectionIn,
    "ask_user": AskUserIn,
    "update_strategy": UpdateStrategyIn,
}


def validate_input(name: str, raw: Any) -> BaseModel:
    model = TOOL_INPUTS.get(name)
    if model is None:
        raise ToolFailure(f"Unknown tool '{name}'")
    if not isinstance(raw, dict):
        raise ToolFailure("Tool input must be a JSON object")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ToolFailure("Invalid tool input: " + "; ".join(e["msg"] + f" at {e['loc']}" for e in exc.errors()))


# ----------------------------------------------------------------- handlers
async def _crawl_site(ctx: ToolContext, args: CrawlSiteIn) -> dict:
    db = get_db()
    org, ws = ctx.organization_id, ctx.workspace_id
    existing = [s for s in await active_sources(org, ws) if s["kind"] == "crawl"]
    if existing and not args.force:
        return {"note": "Pages already stored; not re-crawled.", "sources": [source_summary(s) for s in existing]}

    url = args.url or ctx.workspace["website_url"]
    run_id = new_id()
    await db.workspaces.update_one(
        {"_id": ws, "organization_id": org},
        {"$set": {"crawl": {"run_id": run_id, "status": "running", "started_at": utcnow(), "pages": 0}}},
    )
    await ctx.emit({"type": "crawl", "status": "running", "fetched": 0})

    async def progress(ev: dict) -> None:
        await ctx.emit({"type": "crawl", "status": "running", **ev})

    try:
        result = await Crawler(crawl_config()).crawl(url, on_progress=progress)
    except UnsafeUrlError as exc:
        await db.workspaces.update_one({"_id": ws, "organization_id": org}, {"$set": {"crawl.status": "failed", "crawl.error": str(exc)}})
        await ctx.emit({"type": "crawl", "status": "failed", "error": str(exc)})
        raise ToolFailure(f"Cannot crawl this URL: {exc}")

    docs = [page_to_doc(org, ws, p, "crawl", run_id) for p in result.pages if p.text.strip()]
    if docs:
        await db.sources.update_many({"organization_id": org, "workspace_id": ws, "kind": "crawl"}, {"$set": {"active": False}})
        await db.sources.insert_many(docs)
    status = "done" if docs else "failed"
    await db.workspaces.update_one(
        {"_id": ws, "organization_id": org},
        {
            "$set": {
                "crawl.status": status,
                "crawl.finished_at": utcnow(),
                "crawl.pages": len(docs),
                "crawl.stopped_reason": result.stopped_reason,
                "crawl.errors": [f"{u}: {e}" for u, e in result.errors][:20],
            }
        },
    )
    await ctx.emit({"type": "crawl", "status": status, "fetched": len(docs)})
    await ctx.emit({"type": "sources_changed"})
    return {
        "pages_stored": len(docs),
        "stopped_reason": result.stopped_reason,
        "robots_note": result.robots_note,
        "errors": [f"{u}: {e}" for u, e in result.errors][:10],
        "skipped_count": len(result.skipped),
        "duration_seconds": result.duration_seconds,
        "sources": [
            {**source_summary(d), "image_alt_texts": d["image_alts"][:25] if d["page_type"] in ("home", "customers") else []}
            for d in docs
        ],
    }


async def _fetch_page(ctx: ToolContext, args: FetchPageIn) -> dict:
    try:
        page = await fetch_single_page(args.url, crawl_config())
    except (UnsafeUrlError, FetchError) as exc:
        raise ToolFailure(f"Could not fetch {args.url}: {exc}")
    doc = page_to_doc(ctx.organization_id, ctx.workspace_id, page, "page", None)
    doc["purpose"] = args.purpose
    await get_db().sources.insert_one(doc)
    await ctx.emit({"type": "sources_changed"})
    return {**source_summary(doc), "text": doc["text"][:MAX_CHARS_PER_SOURCE]}


async def _read_sources(ctx: ToolContext, args: ReadSourcesIn) -> dict:
    sources = await active_sources(ctx.organization_id, ctx.workspace_id, include_text=True)
    if not args.source_ids and not args.page_types:
        return {"sources": [source_summary(s) for s in sources]}
    wanted = [
        s for s in sources if s["_id"] in args.source_ids or s.get("page_type") in args.page_types
    ]
    missing = [sid for sid in args.source_ids if sid not in {s["_id"] for s in sources}]
    out, total = [], 0
    for s in wanted:
        if total >= MAX_CHARS_TOTAL:
            out.append({"source_id": s["_id"], "note": "omitted: total size limit reached; request it separately"})
            continue
        text = s.get("text", "")[:MAX_CHARS_PER_SOURCE]
        total += len(text)
        item = {**source_summary(s), "text": text}
        if s.get("image_alts"):
            item["image_alt_texts"] = s["image_alts"][:40]
        out.append(item)
    return {"sources": out, "missing_source_ids": missing}


def _section_view(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("organization_id",)}


async def _save_section(ctx: ToolContext, args: SaveSectionIn) -> dict:
    svc = ctx.sections()
    known = await known_source_ids(ctx.organization_id, ctx.workspace_id)
    try:
        doc, flagged = await svc.save_from_agent(
            args.key, args.body_md, [c.model_dump() for c in args.claims], args.confidence, known
        )
    except SectionError as exc:
        raise ToolFailure(str(exc))
    await ctx.emit({"type": "section", "section": _section_view(doc)})
    if flagged:
        await ctx.emit({"type": "sections_changed"})
    return {"saved": args.key, "status": doc["status"], "version": doc["version"], "flagged_needs_refresh": flagged}


async def _update_strategy(ctx: ToolContext, args: UpdateStrategyIn) -> dict:
    svc = ctx.sections()
    db = get_db()
    if args.action == "confirm_section":
        if not args.section_key:
            raise ToolFailure("section_key is required")
        try:
            doc = await svc.confirm(args.section_key)
        except SectionError as exc:
            raise ToolFailure(str(exc))
        await ctx.emit({"type": "section", "section": _section_view(doc)})
        return {"confirmed": args.section_key}

    stage_key = args.stage or ctx.workspace.get("current_stage")
    stage = STAGE_BY_KEY.get(stage_key or "")
    if stage is None:
        raise ToolFailure(f"Unknown stage '{stage_key}'. Stages: {', '.join(s.key for s in STAGES)}")

    if args.action == "complete_stage":
        by_key = {d["key"]: d for d in await svc.store.list(ctx.workspace_id)}
        status = stage_status(stage, by_key)
        if status != "confirmed":
            pending = [s.key for s in stage.sections if by_key.get(s.key, {}).get("status") != "confirmed"]
            raise ToolFailure(f"Stage '{stage.key}' is not fully confirmed yet. Unconfirmed: {pending}")
        nxt = next_stage(stage.key)
        new_stage = nxt.key if nxt else stage.key
    else:  # set_stage
        if not stage.ready:
            raise ToolFailure(f"Stage '{stage.key}' is not available yet in this version")
        new_stage = stage.key

    await db.workspaces.update_one(
        {"_id": ctx.workspace_id, "organization_id": ctx.organization_id},
        {"$set": {"current_stage": new_stage, "updated_at": utcnow()}},
    )
    ctx.workspace["current_stage"] = new_stage
    await ctx.emit({"type": "workspace_changed"})
    nxt_stage = STAGE_BY_KEY[new_stage]
    return {
        "current_stage": new_stage,
        "stage_available": nxt_stage.ready,
        "note": "" if nxt_stage.ready else f"Stage '{new_stage}' is not available yet in this version; tell the user.",
    }


HANDLERS: dict[str, Callable[[ToolContext, Any], Awaitable[dict]]] = {
    "crawl_site": _crawl_site,
    "fetch_page": _fetch_page,
    "read_sources": _read_sources,
    "save_section": _save_section,
    "update_strategy": _update_strategy,
}

TOOL_LABELS = {
    "crawl_site": "Crawling the website",
    "fetch_page": "Fetching a page",
    "read_sources": "Reading pages",
    "save_section": "Saving a section",
    "update_strategy": "Updating the strategy",
    "ask_user": "Asking you",
}


async def run_tool(ctx: ToolContext, name: str, raw_input: Any) -> tuple[str, bool]:
    """Run a tool. Returns (result_json, is_error)."""
    try:
        args = validate_input(name, raw_input)
        handler = HANDLERS[name]
        result = await handler(ctx, args)
        return json.dumps(result, default=str), False
    except ToolFailure as exc:
        return json.dumps({"error": str(exc)}), True
    except Exception:  # unexpected failure: log it, give the agent a usable message
        log.exception("tool %s failed", name)
        return json.dumps({"error": f"Internal error while running {name}; try again or continue without it."}), True
