"""Polite, bounded, resilient website crawler.

Limits enforced:
- home page + at most `max_pages` internal pages, same site only
- per-request timeout and an overall time budget
- per-page byte cap (response is streamed and cut off at the cap)
- robots.txt rules, HTML only, max 5 redirects, every hop SSRF-checked

Fallbacks (each can be switched off in CrawlConfig; all are off by default and
turned on by the app's settings):
- browser-like request headers, one retry on 429/503
- reader service (renders JavaScript) for pages that are blocked, time out, or
  have almost no text (JavaScript-built pages)
- www / non-www / http variants when the home page can't be reached
- likely pages (/pricing, /about, ...) when the home page exposes few links
"""
from __future__ import annotations

import asyncio
import heapq
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

from .extract import extract, markdown_to_text
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
RETRY_STATUS = {429, 503}
# Errors where a rendering reader may still succeed (blocked, rate limited, slow, server trouble).
READER_RETRY_STATUS = {401, 403, 406, 409, 429, 451, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526}
GUESS_PATHS = (
    "/pricing", "/plans", "/product", "/products", "/features", "/platform", "/solutions",
    "/customers", "/case-studies", "/use-cases", "/integrations", "/about", "/about-us", "/company",
)
CHALLENGE_TITLES = ("just a moment", "attention required", "access denied", "verify you are human", "are you a robot", "security check")
CHALLENGE_MARKERS = ("cf-chl-", "challenge-platform", "_incapsula_resource", "px-captcha", "captcha-delivery.com")

ProgressCallback = Callable[[dict], Awaitable[None]]


@dataclass
class CrawlConfig:
    max_pages: int = 25
    timeout_seconds: float = 10.0
    total_budget_seconds: float = 90.0
    max_bytes: int = 2_000_000
    concurrency: int = 4
    user_agent: str = "GTMStrategyBot/0.1"  # matched against robots.txt rules
    max_depth: int = 2
    browser_user_agent: str | None = None  # User-Agent header; defaults to user_agent
    reader_url: str | None = None  # e.g. "https://r.jina.ai/"; None turns the reader off
    reader_api_key: str | None = None
    reader_max_pages: int = 12
    reader_timeout_seconds: float = 30.0
    min_good_chars: int = 400  # below this a page counts as "thin" and the reader is tried
    guess_paths: bool = False
    try_host_variants: bool = False


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
    via: str = "direct"  # direct | reader


@dataclass
class CrawlResult:
    start_url: str
    pages: list[PageResult] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (url, error)
    notes: list[str] = field(default_factory=list)
    robots_note: str = ""
    duration_seconds: float = 0.0
    stopped_reason: str = ""


class FetchError(Exception):
    def __init__(self, message: str, reader_may_help: bool = False, status: int | None = None):
        super().__init__(message)
        self.reader_may_help = reader_may_help
        self.status = status


def is_challenge_page(html: str, title: str) -> bool:
    t = title.strip().lower()
    if any(t.startswith(c) for c in CHALLENGE_TITLES):
        return True
    head = html[:20_000].lower()
    return any(m in head for m in CHALLENGE_MARKERS) and len(html) < 60_000


def host_variants(url: str) -> list[str]:
    """Other spellings of a start URL to try: www toggled, then plain http."""
    parts = urlsplit(url)
    host = parts.netloc
    other = host[4:] if host.startswith("www.") else f"www.{host}"
    out = [urlunsplit((parts.scheme, other, parts.path, parts.query, ""))]
    if parts.scheme == "https":
        out += [urlunsplit(("http", host, parts.path, parts.query, "")), urlunsplit(("http", other, parts.path, parts.query, ""))]
    return out


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
        self._reader_used = 0

    @property
    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.config.browser_user_agent or self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    # ------------------------------------------------------------------ fetch
    async def _fetch(self, client: httpx.AsyncClient, url: str) -> tuple[str, int, str, int, bool]:
        """Fetch one HTML page. Returns (final_url, status, html, bytes, truncated)."""
        current = url
        retried = False
        hops = 0
        while hops <= MAX_REDIRECTS:
            await assert_public_url(current, self._resolver)
            req = client.build_request("GET", current, headers=self.headers)
            try:
                resp = await client.send(req, stream=True)
            except httpx.TimeoutException as exc:
                raise FetchError("timed out", reader_may_help=True) from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"network error ({type(exc).__name__})", reader_may_help=True) from exc
            try:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchError("redirect without location")
                    current = urljoin(current, location)
                    hops += 1
                    continue
                if resp.status_code in RETRY_STATUS and not retried:
                    retried = True
                    await asyncio.sleep(1.5)
                    continue
                if resp.status_code >= 400:
                    raise FetchError(
                        f"HTTP {resp.status_code}",
                        reader_may_help=resp.status_code in READER_RETRY_STATUS,
                        status=resp.status_code,
                    )
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

    def _reader_available(self) -> bool:
        return bool(self.config.reader_url) and self._reader_used < self.config.reader_max_pages

    async def _read_via_reader(self, client: httpx.AsyncClient, url: str, page_type: str) -> PageResult:
        """Fetch a page through the rendering reader (handles JavaScript-built and many protected pages)."""
        await assert_public_url(url, self._resolver)
        self._reader_used += 1
        headers = {"Accept": "application/json", "X-With-Links-Summary": "true", "X-Timeout": "25"}
        if self.config.reader_api_key:
            headers["Authorization"] = f"Bearer {self.config.reader_api_key}"
        endpoint = self.config.reader_url.rstrip("/") + "/" + quote(url, safe=":/?&=%#@+,;~")
        try:
            resp = await client.get(endpoint, headers=headers, timeout=self.config.reader_timeout_seconds, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise FetchError("reader timed out") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"reader network error ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise FetchError(f"reader HTTP {resp.status_code}")
        try:
            data = (resp.json() or {}).get("data") or {}
        except ValueError as exc:
            raise FetchError("reader returned an unreadable response") from exc
        markdown = data.get("content") or ""
        text, image_alts = markdown_to_text(markdown)
        title = (data.get("title") or "").strip()
        if is_challenge_page(markdown, title):
            raise FetchError("blocked by bot protection (reader too)")
        raw_links = data.get("links") or {}
        if isinstance(raw_links, dict):
            link_list = list(raw_links.values())
        else:
            link_list = [ln[1] if isinstance(ln, (list, tuple)) and len(ln) > 1 else ln for ln in raw_links]
        final_url = data.get("url") or url
        links = [urljoin(final_url, ln) for ln in link_list if isinstance(ln, str)]
        return PageResult(
            url=url,
            final_url=final_url,
            status=200,
            page_type=page_type,
            title=title,
            description=(data.get("description") or "").strip(),
            text=text[:50_000],
            image_alts=image_alts[:60],
            bytes=len(markdown.encode()),
            truncated=len(text) > 50_000,
            links=links,
            via="reader",
        )

    async def _page(self, client: httpx.AsyncClient, url: str, page_type: str) -> PageResult:
        page: PageResult | None = None
        direct_error: FetchError | None = None
        body_chars = 0
        try:
            final_url, status, html, size, truncated = await asyncio.wait_for(
                self._fetch(client, url), timeout=self.config.timeout_seconds
            )
            ex = extract(html, final_url)
            body_chars = ex.body_chars
            if is_challenge_page(html, ex.title):
                direct_error = FetchError("blocked by bot protection", reader_may_help=True)
            else:
                page = PageResult(
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
        except asyncio.TimeoutError:
            direct_error = FetchError("timed out", reader_may_help=True)
        except FetchError as exc:
            direct_error = exc

        thin = page is not None and body_chars < self.config.min_good_chars
        wants_reader = thin or (page is None and direct_error is not None and direct_error.reader_may_help)
        if wants_reader and self._reader_available():
            try:
                rendered = await self._read_via_reader(client, url, page_type)
            except FetchError as exc:
                if page is None:
                    raise FetchError(f"{direct_error}; reader fallback failed: {exc}") from exc
            else:
                if page is None or len(rendered.text) > body_chars:
                    if page is not None:  # keep links and structured data found in the raw HTML too
                        rendered.links = list(dict.fromkeys(rendered.links + page.links))
                        extra = page.text[body_chars:].strip()
                        if extra:
                            rendered.text = f"{rendered.text}\n\n{extra}"
                    page = rendered
        if page is None:
            assert direct_error is not None
            raise direct_error
        return page

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
                    headers=self.headers,
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

    async def _resolve_start(self, start_url: str, result: CrawlResult) -> str:
        """Check the start URL is public; if its host doesn't resolve, try the www/non-www spelling."""
        try:
            await assert_public_url(start_url, self._resolver)
            return start_url
        except UnsafeUrlError as exc:
            if not (self.config.try_host_variants and "Could not resolve" in str(exc)):
                raise
            alt = host_variants(start_url)[0]
            try:
                await assert_public_url(alt, self._resolver)
            except UnsafeUrlError:
                raise exc
            result.notes.append(f"{urlsplit(start_url).hostname} did not resolve; used {urlsplit(alt).hostname}")
            return alt

    async def _home(self, client: httpx.AsyncClient, start_url: str, result: CrawlResult) -> PageResult | None:
        candidates = [start_url] + (host_variants(start_url) if self.config.try_host_variants else [])
        first_error = ""
        for i, cand in enumerate(candidates):
            try:
                home = await self._page(client, cand, "home")
                if i:
                    result.notes.append(f"home page read from {cand} ({start_url} failed: {first_error})")
                if home.via == "reader":
                    result.notes.append("home page read through the rendering reader (site is JavaScript-heavy or blocks bots)")
                return home
            except (FetchError, UnsafeUrlError) as exc:
                if not first_error:
                    first_error = str(exc)
                result.errors.append((cand, str(exc)))
        result.stopped_reason = f"home page could not be fetched: {first_error}"
        return None

    # ----------------------------------------------------------------- crawl
    async def crawl(self, raw_url: str, on_progress: ProgressCallback | None = None) -> CrawlResult:
        start_url = normalize_start_url(raw_url)  # raises UnsafeUrlError for bad input
        started = self._clock()
        result = CrawlResult(start_url=start_url)
        start_url = await self._resolve_start(start_url, result)

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
            robots: RobotsPolicy = await fetch_robots(client, origin, self.config.timeout_seconds, self.headers)
            result.robots_note = robots.reason
            ua = self.config.user_agent

            if not robots.allowed(start_url, ua):
                result.skipped.append((start_url, "blocked by robots.txt"))
                result.stopped_reason = "robots.txt does not allow crawling this site"
                return result

            # Home page first.
            home = await self._home(client, start_url, result)
            if home is None:
                return result
            result.pages.append(home)
            await progress({"fetched": 1, "url": home.final_url, "title": home.title})

            root_host = urlsplit(home.final_url).hostname or parts.hostname or ""
            home_path = urlsplit(home.final_url).path
            home_is_localized = bool(re.match(r"^/[a-z]{2}(?:[-_][a-z]{2})?/?$", home_path, re.I))
            home_origin = "{0.scheme}://{0.netloc}".format(urlsplit(home.final_url))

            seen: set[str] = {canonical(start_url), canonical(home.final_url)}
            heap: list[tuple[int, int, str, str, int]] = []  # (-score, order, url, type, depth)
            order = 0
            type_counts: dict[str, int] = {}
            guessed: set[str] = set()

            def enqueue(url: str, depth: int, penalty: int = 0) -> bool:
                nonlocal order
                url = url.split("#")[0]
                if not url.startswith(("http://", "https://")) or not same_site(url, root_host):
                    return False
                key = canonical(url)
                if key in seen:
                    return False
                seen.add(key)
                reason = should_skip(url, home_is_localized)
                if reason:
                    result.skipped.append((url, reason))
                    return False
                page_type, score = classify(url)
                order += 1
                heapq.heappush(heap, (-(score - penalty), order, url, page_type, depth))
                return True

            for link in home.links:
                enqueue(link, 1)
            sitemap_candidates = robots.sitemaps or [origin + "/sitemap.xml"]
            for url in await self._sitemap_urls(client, sitemap_candidates, root_host):
                enqueue(url, 1)
            if self.config.guess_paths and len(heap) < 8:
                for path in GUESS_PATHS:
                    url = home_origin + path
                    if enqueue(url, 1, penalty=5):
                        guessed.add(url)
                if guessed:
                    result.notes.append("few links found on the home page; tried common pages like /pricing and /about")

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
                for (url, page_type, depth), outcome in zip(batch, outcomes):
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
                    elif url in guessed:
                        type_counts[page_type] -= 1  # a missing guess shouldn't use up the type's quota
                        result.skipped.append((url, f"guessed page not available ({outcome[1]})"))
                    else:
                        result.errors.append(outcome)
            else:
                if not result.stopped_reason:
                    result.stopped_reason = (
                        "page limit reached" if len(result.pages) - 1 >= self.config.max_pages else "no more pages"
                    )
            via_reader = sum(1 for p in result.pages if p.via == "reader")
            if via_reader:
                result.notes.append(f"{via_reader} page(s) read through the rendering reader")
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
        robots = await fetch_robots(c, f"{parts.scheme}://{parts.netloc}", config.timeout_seconds, crawler.headers)
        if not robots.allowed(url, config.user_agent):
            raise FetchError("blocked by robots.txt")
        page_type, _ = classify(url)
        return await crawler._page(c, url, page_type)
    except asyncio.TimeoutError as exc:
        raise FetchError("timed out") from exc
    finally:
        if own:
            await c.aclose()
