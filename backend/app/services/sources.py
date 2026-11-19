"""Stored sources: crawled pages, single fetched pages, and pasted context."""
from __future__ import annotations

import hashlib

from ..crawler import CrawlConfig, PageResult
from ..config import get_settings
from ..db import get_db, new_id, utcnow


def crawl_config() -> CrawlConfig:
    s = get_settings()
    return CrawlConfig(
        max_pages=s.crawl_max_pages,
        timeout_seconds=s.crawl_timeout_seconds,
        total_budget_seconds=s.crawl_total_budget_seconds,
        max_bytes=s.crawl_max_bytes,
        concurrency=s.crawl_concurrency,
        user_agent=s.crawl_user_agent,
    )


def page_to_doc(org: str, ws: str, page: PageResult, kind: str, crawl_run_id: str | None) -> dict:
    return {
        "_id": new_id(),
        "organization_id": org,
        "workspace_id": ws,
        "kind": kind,  # crawl | page | paste
        "url": page.final_url,
        "title": page.title,
        "description": page.description,
        "page_type": page.page_type,
        "text": page.text,
        "image_alts": page.image_alts,
        "content_hash": hashlib.sha256(page.text.encode()).hexdigest(),
        "bytes": page.bytes,
        "truncated": page.truncated,
        "crawl_run_id": crawl_run_id,
        "active": True,
        "fetched_at": utcnow(),
    }


def paste_doc(org: str, ws: str, title: str, text: str) -> dict:
    return {
        "_id": new_id(),
        "organization_id": org,
        "workspace_id": ws,
        "kind": "paste",
        "url": None,
        "title": title,
        "description": "",
        "page_type": "user_context",
        "text": text,
        "image_alts": [],
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "bytes": len(text.encode()),
        "truncated": False,
        "crawl_run_id": None,
        "active": True,
        "fetched_at": utcnow(),
    }


async def active_sources(org: str, ws: str, include_text: bool = False) -> list[dict]:
    projection = None if include_text else {"text": 0}
    cur = get_db().sources.find({"organization_id": org, "workspace_id": ws, "active": True}, projection).sort("fetched_at", 1)
    return [d async for d in cur]


async def known_source_ids(org: str, ws: str) -> set[str]:
    cur = get_db().sources.find({"organization_id": org, "workspace_id": ws}, {"_id": 1})
    return {d["_id"] async for d in cur}


def source_summary(doc: dict) -> dict:
    return {
        "source_id": doc["_id"],
        "kind": doc["kind"],
        "url": doc.get("url"),
        "title": doc.get("title", ""),
        "page_type": doc.get("page_type", ""),
        "chars": len(doc.get("text", "")) if "text" in doc else None,
        "description": (doc.get("description") or "")[:200],
    }
