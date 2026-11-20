"""Crawler fallbacks: rendering reader, bot-protection pages, host variants, guessed pages,
structured data. No real network is used (respx mocks every request)."""
from __future__ import annotations

import json

import httpx
import respx

from app.crawler import CrawlConfig, Crawler
from app.crawler.crawler import host_variants, is_challenge_page
from app.crawler.extract import extract, markdown_to_text

SITE = "https://acme.test"
READER = "https://reader.test/"
LONG = "Acme helps finance teams close the books faster. " * 20  # well over min_good_chars


async def resolver(host: str) -> list[str]:
    if host.startswith("nodns"):
        from app.crawler import UnsafeUrlError

        raise UnsafeUrlError(f"Could not resolve host '{host}'")
    return ["93.184.216.34"]


def html_page(body: str, title: str = "Acme", head: str = "") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/html"},
        text=f"<html><head><title>{title}</title>{head}</head><body><main>{body}</main></body></html>",
    )


def reader_response(content: str, title: str = "Acme", links: dict | None = None, url: str = f"{SITE}/") -> httpx.Response:
    return httpx.Response(
        200, json={"code": 200, "data": {"title": title, "url": url, "content": content, "links": links or {}}}
    )


def cfg(**kw) -> CrawlConfig:
    base = dict(max_pages=10, timeout_seconds=5, total_budget_seconds=60, max_bytes=200_000, concurrency=2,
                reader_url=READER, min_good_chars=200)
    base.update(kw)
    return CrawlConfig(**base)


def basic_site(robots_status: int = 404) -> None:
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(robots_status))
    respx.get(f"{SITE}/sitemap.xml").mock(return_value=httpx.Response(404))


async def crawl(config: CrawlConfig, url: str = SITE):
    async with httpx.AsyncClient() as client:
        return await Crawler(config, client=client, resolver=resolver).crawl(url)


@respx.mock
async def test_blocked_home_page_is_read_through_reader():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=httpx.Response(403, text="Forbidden"))
    reader = respx.get(url__startswith=READER).mock(
        return_value=reader_response(LONG, links={"Pricing": f"{SITE}/pricing"})
    )
    result = await crawl(cfg(max_pages=0))
    assert reader.called
    assert len(result.pages) == 1 and result.pages[0].via == "reader"
    assert "finance teams" in result.pages[0].text
    assert any("reader" in n for n in result.notes)


@respx.mock
async def test_javascript_only_page_uses_reader_and_keeps_links():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=html_page('<div id="root"></div><a href="/pricing">Pricing</a>'))
    respx.get(url__startswith=READER + SITE + "/pricing").mock(return_value=reader_response("Plans from $49 per seat. " * 20, url=f"{SITE}/pricing"))
    respx.get(url__startswith=READER).mock(return_value=reader_response(LONG))
    respx.get(f"{SITE}/pricing").mock(return_value=html_page("<div id='root'></div>"))
    result = await crawl(cfg())
    assert [p.page_type for p in result.pages] == ["home", "pricing"]
    assert all(p.via == "reader" for p in result.pages)
    assert "$49" in result.pages[1].text


@respx.mock
async def test_bot_challenge_page_is_not_stored_as_content():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=html_page("Checking your browser", title="Just a moment..."))
    respx.get(url__startswith=READER).mock(return_value=reader_response(LONG))
    result = await crawl(cfg(max_pages=0))
    assert result.pages[0].via == "reader"
    assert "Checking your browser" not in result.pages[0].text


@respx.mock
async def test_reader_off_reports_the_original_error():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=httpx.Response(403))
    result = await crawl(cfg(reader_url=None, max_pages=0))
    assert result.pages == []
    assert "HTTP 403" in result.stopped_reason


@respx.mock
async def test_reader_failure_is_reported_with_both_errors():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=httpx.Response(403))
    respx.get(url__startswith=READER).mock(return_value=httpx.Response(451))
    result = await crawl(cfg(max_pages=0))
    assert result.pages == []
    assert "HTTP 403" in result.stopped_reason and "reader" in result.stopped_reason


@respx.mock
async def test_404_does_not_waste_a_reader_call():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=httpx.Response(404))
    reader = respx.get(url__startswith=READER).mock(return_value=reader_response(LONG))
    result = await crawl(cfg(max_pages=0))
    assert not reader.called
    assert "HTTP 404" in result.stopped_reason


@respx.mock
async def test_reader_page_cap_is_respected():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=html_page(LONG + "".join(f'<a href="/p{i}">p</a>' for i in range(6))))
    for i in range(6):
        respx.get(f"{SITE}/p{i}").mock(return_value=httpx.Response(403))
    reader = respx.get(url__startswith=READER).mock(return_value=reader_response(LONG))
    await crawl(cfg(reader_max_pages=2))
    assert reader.call_count == 2


@respx.mock
async def test_www_variant_is_tried_when_home_fails():
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(f"{SITE}/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get(f"{SITE}/").mock(side_effect=httpx.ConnectError("refused"))
    respx.get("https://www.acme.test/").mock(return_value=html_page(LONG))
    respx.get("https://www.acme.test/sitemap.xml").mock(return_value=httpx.Response(404))
    result = await crawl(cfg(reader_url=None, try_host_variants=True, max_pages=0))
    assert len(result.pages) == 1 and result.pages[0].final_url == "https://www.acme.test/"
    assert any("www.acme.test" in n for n in result.notes)


async def test_unresolvable_host_falls_back_to_www():
    calls = []

    async def dns(host: str) -> list[str]:
        calls.append(host)
        if host == "acme.test":
            from app.crawler import UnsafeUrlError

            raise UnsafeUrlError("Could not resolve host 'acme.test'")
        return ["93.184.216.34"]

    with respx.mock:
        respx.get("https://www.acme.test/robots.txt").mock(return_value=httpx.Response(404))
        respx.get("https://www.acme.test/sitemap.xml").mock(return_value=httpx.Response(404))
        respx.get("https://www.acme.test/").mock(return_value=html_page(LONG))
        async with httpx.AsyncClient() as client:
            result = await Crawler(cfg(reader_url=None, try_host_variants=True, max_pages=0), client=client, resolver=dns).crawl("acme.test")
    assert len(result.pages) == 1
    assert "www.acme.test" in calls


@respx.mock
async def test_common_pages_are_guessed_when_home_has_few_links():
    basic_site()
    respx.get(f"{SITE}/").mock(return_value=html_page(LONG))
    respx.get(f"{SITE}/pricing").mock(return_value=html_page("Plans from $49 " * 30))
    respx.get(url__regex=rf"{SITE}/(?!pricing$).+").mock(return_value=httpx.Response(404))
    result = await crawl(cfg(reader_url=None, guess_paths=True))
    assert "pricing" in [p.page_type for p in result.pages]
    assert not result.errors  # missing guesses are skipped, not errors
    assert any("guessed page not available" in r for _, r in result.skipped)


@respx.mock
async def test_retry_once_on_429():
    basic_site()
    respx.get(f"{SITE}/").mock(side_effect=[httpx.Response(429), html_page(LONG)])
    result = await crawl(cfg(reader_url=None, max_pages=0))
    assert len(result.pages) == 1


@respx.mock
async def test_browser_headers_are_sent():
    basic_site()
    route = respx.get(f"{SITE}/").mock(return_value=html_page(LONG))
    await crawl(cfg(reader_url=None, max_pages=0, browser_user_agent="Mozilla/5.0 Test"))
    sent = route.calls[0].request.headers
    assert sent["user-agent"] == "Mozilla/5.0 Test"
    assert "text/html" in sent["accept"] and sent["accept-language"]


# ------------------------------------------------------------- helpers
def test_structured_data_is_added_to_page_text():
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "name": "skip me"},
            {"@type": "SoftwareApplication", "name": "Acme Books", "applicationCategory": "FinanceApplication",
             "offers": {"@type": "Offer", "price": "49", "priceCurrency": "USD"}},
        ],
    }
    head = f'<script type="application/ld+json">{json.dumps(ld)}</script><meta property="og:site_name" content="Acme">'
    ex = extract(f"<html><head><title>A</title>{head}</head><body><div id=root></div></body></html>", SITE)
    assert "Acme Books" in ex.text and "price: 49" in ex.text and "priceCurrency: USD" in ex.text
    assert "skip me" not in ex.text
    assert "og:site_name: Acme" in ex.text
    assert ex.body_chars < 50  # structured data doesn't make an empty page look full


def test_markdown_to_text_keeps_labels_and_alts():
    text, alts = markdown_to_text("# Acme\n\n![Image 1: Stripe logo](https://x/y.png)\n\nSee [pricing](https://acme.test/pricing).")
    assert "See pricing." in text and "https://" not in text
    assert alts == ["Stripe logo"]


def test_challenge_detection():
    assert is_challenge_page("<html>...</html>", "Just a moment...")
    assert is_challenge_page('<script src="/cdn-cgi/challenge-platform/x.js"></script>', "Acme")
    assert not is_challenge_page("<html>" + "real content " * 5000 + "challenge-platform</html>", "Acme")
    assert not is_challenge_page("<html>Welcome</html>", "Acme - Accounting")


def test_host_variants():
    assert host_variants("https://acme.com/") == ["https://www.acme.com/", "http://acme.com/", "http://www.acme.com/"]
    assert host_variants("https://www.acme.com/")[0] == "https://acme.com/"
