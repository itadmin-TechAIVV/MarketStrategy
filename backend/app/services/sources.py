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
        browser_user_agent=s.crawl_browser_user_agent,
        reader_url=s.crawl_reader_url or None,
        reader_api_key=s.jina_api_key.get_secret_value() if s.jina_api_key else None,
        reader_max_pages=s.crawl_reader_max_pages,
        guess_paths=s.crawl_guess_paths,
        try_host_variants=True,
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
        "via": page.via,
        "crawl_run_id": crawl_run_id,
        "active": True,
        "fetched_at": utcnow(),
    }


def research_doc(org: str, ws: str, query: str, answer: str, web_sources: list[dict]) -> dict:
    """A web-research answer (Gemini + Google Search) stored as one citable source."""
    lines = [f"Research question: {query}", "", answer]
    if web_sources:
        lines += ["", "Web sources:"] + [f"- {s.get('title') or s['url']}: {s['url']}" for s in web_sources]
    text = "\n".join(lines)
    return {
        "_id": new_id(),
        "organization_id": org,
        "workspace_id": ws,
        "kind": "search",
        "url": None,
        "title": f"Web research: {query[:120]}",
        "description": ", ".join((s.get("title") or "") for s in web_sources[:5])[:200],
        "page_type": "web_research",
        "text": text,
        "image_alts": [],
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "bytes": len(text.encode()),
        "truncated": False,
        "crawl_run_id": None,
        "active": True,
        "fetched_at": utcnow(),
        "web_sources": web_sources,
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
