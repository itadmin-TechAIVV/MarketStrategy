"""Polite, bounded website crawler.

Limits enforced:
- home page + at most `max_pages` internal pages, same site only
- per-request timeout and an overall time budget
- per-page byte cap (response is streamed and cut off at the cap)
- robots.txt rules, HTML only, max 5 redirects, every hop SSRF-checked
"""
from __future__ import annotations

import asyncio
import heapq
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import httpx

from .extract import extract
from .prioritize import TYPE_CAPS, classify, should_skip
from .robots import RobotsPolicy, fetch_robots
from .safety import (
    Resolver,
    UnsafeUrlError,
    assert_public_url,
    canonical,
    normalize_start_url,
    same_site,
    system_resolver,
)

MAX_REDIRECTS = 5
MAX_SITEMAP_URLS = 500
HTML_TYPES = ("text/html", "application/xhtml+xml")

ProgressCallback = Callable[[dict], Awaitable[None]]


@dataclass
class CrawlConfig:
    max_pages: int = 25
    timeout_seconds: float = 10.0
    total_budget_seconds: float = 90.0
    max_bytes: int = 2_000_000
    concurrency: int = 4
    user_agent: str = "GTMStrategyBot/0.1"
    max_depth: int = 2


@dataclass
class PageResult:
    url: str
    final_url: str
    status: int
    page_type: str
    title: str = ""
    description: str = ""
    text: str = ""
    image_alts: list[str] = field(default_factory=list)
    bytes: int = 0
    truncated: bool = False
    links: list[str] = field(default_factory=list)


@dataclass
class CrawlResult:
    start_url: str
    pages: list[PageResult] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (url, error)
    robots_note: str = ""
    duration_seconds: float = 0.0
    stopped_reason: str = ""


class FetchError(Exception):
    pass


class Crawler:
    def __init__(
        self,
        config: CrawlConfig,
        client: httpx.AsyncClient | None = None,
        resolver: Resolver | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.config = config
        self._client = client
        self._resolver = resolver or system_resolver
        self._clock = clock

    # ------------------------------------------------------------------ fetch
    async def _fetch(self, client: httpx.AsyncClient, url: str) -> tuple[str, int, str, int, bool]:
        """Fetch one HTML page. Returns (final_url, status, html, bytes, truncated)."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await assert_public_url(current, self._resolver)
            req = client.build_request("GET", current, headers={"User-Agent": self.config.user_agent})
            try:
                resp = await client.send(req, stream=True)
            except httpx.TimeoutException as exc:
                raise FetchError("timed out") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"network error ({type(exc).__name__})") from exc
            try:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchError("redirect without location")
                    current = urljoin(current, location)
                    continue
                if resp.status_code >= 400:
                    raise FetchError(f"HTTP {resp.status_code}")
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and ctype not in HTML_TYPES:
                    raise FetchError(f"not HTML ({ctype})")
                chunks: list[bytes] = []
                size = 0
                truncated = False
                async for chunk in resp.aiter_bytes():
                    remaining = self.config.max_bytes - size
                    if len(chunk) >= remaining:
                        chunks.append(chunk[:remaining])
                        size += remaining
                        truncated = True
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                encoding = resp.encoding or "utf-8"
                html = b"".join(chunks).decode(encoding, errors="replace")
                return str(resp.url), resp.status_code, html, size, truncated
            finally:
                await resp.aclose()
        raise FetchError("too many redirects")

    async def _page(self, client: httpx.AsyncClient, url: str, page_type: str) -> PageResult:
        final_url, status, html, size, truncated = await asyncio.wait_for(
            self._fetch(client, url), timeout=self.config.timeout_seconds
        )
        ex = extract(html, final_url)
        return PageResult(
            url=url,
            final_url=final_url,
            status=status,
            page_type=page_type,
            title=ex.title,
            description=ex.description,
            text=ex.text,
            image_alts=ex.image_alts,
            bytes=size,
            truncated=truncated,
            links=ex.links,
        )

    # --------------------------------------------------------------- sitemap
    async def _sitemap_urls(self, client: httpx.AsyncClient, sitemap_urls: list[str], root_host: str) -> list[str]:
        found: list[str] = []
        queue = list(dict.fromkeys(sitemap_urls))[:3]
        fetched = 0
        while queue and fetched < 4 and len(found) < MAX_SITEMAP_URLS:
            sm_url = queue.pop(0)
            fetched += 1
            try:
                await assert_public_url(sm_url, self._resolver)
                resp = await client.get(
                    sm_url,
                    headers={"User-Agent": self.config.user_agent},
                    timeout=self.config.timeout_seconds,
                    follow_redirects=False,
                )
                if resp.status_code != 200 or len(resp.content) > self.config.max_bytes:
                    continue
                root = ElementTree.fromstring(resp.content)
            except (httpx.HTTPError, ElementTree.ParseError, UnsafeUrlError):
                continue
            locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
            if root.tag.endswith("sitemapindex"):
                # Prefer page/product sitemaps over post archives.
                locs.sort(key=lambda u: (("post" in u or "blog" in u), len(u)))
                queue.extend(locs[:3])
            else:
                found.extend(u for u in locs if same_site(u, root_host))
        return found[:MAX_SITEMAP_URLS]

    # ----------------------------------------------------------------- crawl
    async def crawl(self, raw_url: str, on_progress: ProgressCallback | None = None) -> CrawlResult:
        start_url = normalize_start_url(raw_url)  # raises UnsafeUrlError for bad input
        await assert_public_url(start_url, self._resolver)

        started = self._clock()
        result = CrawlResult(start_url=start_url)
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.timeout_seconds, follow_redirects=False)

        async def progress(event: dict) -> None:
            if on_progress:
                try:
                    await on_progress(event)
                except Exception:
                    pass

        try:
            parts = urlsplit(start_url)
            origin = f"{parts.scheme}://{parts.netloc}"
            robots: RobotsPolicy = await fetch_robots(client, origin, self.config.timeout_seconds)
            result.robots_note = robots.reason
            ua = self.config.user_agent

            if not robots.allowed(start_url, ua):
                result.skipped.append((start_url, "blocked by robots.txt"))
                result.stopped_reason = "robots.txt does not allow crawling this site"
                return result

            # Home page first.
            try:
                home = await self._page(client, start_url, "home")
            except (FetchError, UnsafeUrlError, asyncio.TimeoutError) as exc:
                msg = "timed out" if isinstance(exc, asyncio.TimeoutError) else str(exc)
                result.errors.append((start_url, msg))
                result.stopped_reason = f"home page could not be fetched: {msg}"
                return result
            result.pages.append(home)
            await progress({"fetched": 1, "url": home.final_url, "title": home.title})

            root_host = urlsplit(home.final_url).hostname or parts.hostname or ""
            home_path = urlsplit(home.final_url).path
            home_is_localized = bool(re.match(r"^/[a-z]{2}(?:[-_][a-z]{2})?/?$", home_path, re.I))

            seen: set[str] = {canonical(start_url), canonical(home.final_url)}
            heap: list[tuple[int, int, str, str, int]] = []  # (-score, order, url, type, depth)
            order = 0
            type_counts: dict[str, int] = {}

            def enqueue(url: str, depth: int) -> None:
                nonlocal order
                url = url.split("#")[0]
                if not url.startswith(("http://", "https://")) or not same_site(url, root_host):
                    return
                key = canonical(url)
                if key in seen:
                    return
                seen.add(key)
                reason = should_skip(url, home_is_localized)
                if reason:
                    result.skipped.append((url, reason))
                    return
                page_type, score = classify(url)
                order += 1
                heapq.heappush(heap, (-score, order, url, page_type, depth))

            for link in home.links:
                enqueue(link, 1)
            sitemap_candidates = robots.sitemaps or [origin + "/sitemap.xml"]
            for url in await self._sitemap_urls(client, sitemap_candidates, root_host):
                enqueue(url, 1)

            sem = asyncio.Semaphore(max(1, self.config.concurrency))

            async def fetch_one(url: str, page_type: str) -> PageResult | tuple[str, str]:
                async with sem:
                    try:
                        return await self._page(client, url, page_type)
                    except asyncio.TimeoutError:
                        return (url, "timed out")
                    except (FetchError, UnsafeUrlError) as exc:
                        return (url, str(exc))

            while heap and len(result.pages) - 1 < self.config.max_pages:
                if self._clock() - started > self.config.total_budget_seconds:
                    result.stopped_reason = "time budget reached"
                    break
                batch: list[tuple[str, str, int]] = []
                slots = self.config.max_pages - (len(result.pages) - 1)
                while heap and len(batch) < min(self.config.concurrency, slots):
                    _, _, url, page_type, depth = heapq.heappop(heap)
                    if not robots.allowed(url, ua):
                        result.skipped.append((url, "blocked by robots.txt"))
                        continue
                    if type_counts.get(page_type, 0) >= TYPE_CAPS.get(page_type, 3):
                        result.skipped.append((url, f"enough '{page_type}' pages"))
                        continue
                    type_counts[page_type] = type_counts.get(page_type, 0) + 1
                    batch.append((url, page_type, depth))
                if not batch:
                    break
                outcomes = await asyncio.gather(*(fetch_one(u, t) for u, t, _ in batch))
                for (url, _, depth), outcome in zip(batch, outcomes):
                    if isinstance(outcome, PageResult):
                        if canonical(outcome.final_url) != canonical(url) and canonical(outcome.final_url) in {
                            canonical(p.final_url) for p in result.pages
                        }:
                            result.skipped.append((url, "duplicate after redirect"))
                            continue
                        result.pages.append(outcome)
                        await progress({"fetched": len(result.pages), "url": outcome.final_url, "title": outcome.title})
                        if depth < self.config.max_depth:
                            for link in outcome.links:
                                enqueue(link, depth + 1)
                    else:
                        result.errors.append(outcome)
            else:
                if not result.stopped_reason:
                    result.stopped_reason = (
                        "page limit reached" if len(result.pages) - 1 >= self.config.max_pages else "no more pages"
                    )
            return result
        finally:
            result.duration_seconds = round(self._clock() - started, 2)
            if own_client:
                await client.aclose()


async def fetch_single_page(
    raw_url: str, config: CrawlConfig, client: httpx.AsyncClient | None = None, resolver: Resolver | None = None
) -> PageResult:
    """Fetch one page (used for competitor URLs or pages outside the main crawl). Respects robots.txt."""
    url = normalize_start_url(raw_url)
    crawler = Crawler(config, client=client, resolver=resolver)
    own = client is None
    c = client or httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False)
    try:
        await assert_public_url(url, crawler._resolver)
        parts = urlsplit(url)
        robots = await fetch_robots(c, f"{parts.scheme}://{parts.netloc}", config.timeout_seconds)
        if not robots.allowed(url, config.user_agent):
            raise FetchError("blocked by robots.txt")
        page_type, _ = classify(url)
        return await crawler._page(c, url, page_type)
    except asyncio.TimeoutError as exc:
        raise FetchError("timed out") from exc
    finally:
        if own:
            await c.aclose()
