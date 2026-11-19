"""Crawler tests: limits, robots.txt, bad URLs, SSRF, prioritisation. No real network is used."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.crawler import CrawlConfig, Crawler, FetchError, UnsafeUrlError, fetch_single_page, normalize_start_url
from app.crawler.prioritize import classify, should_skip

PUBLIC_IP = "93.184.216.34"
SITE = "https://acme.test"


async def public_resolver(host: str) -> list[str]:
    if host.startswith("internal"):
        return ["10.0.0.5"]
    if host.startswith("loopback"):
        return ["127.0.0.1"]
    return [PUBLIC_IP]


def html(body: str, title: str = "Acme") -> str:
    return f"<html><head><title>{title}</title></head><body><main>{body}</main></body></html>"


def links(*paths: str) -> str:
    return "".join(f'<a href="{p}">{p}</a>' for p in paths)


def page(body: str = "", title: str = "Acme", **kw) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=html(body, title), **kw)


def config(**overrides) -> CrawlConfig:
    base = dict(max_pages=25, timeout_seconds=5, total_budget_seconds=60, max_bytes=200_000, concurrency=2)
    base.update(overrides)
    return CrawlConfig(**base)


def mock_site(router: respx.MockRouter, robots: str | None = "User-agent: *\nAllow: /\n", robots_status: int = 200):
    if robots is None:
        router.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(404))
    else:
        router.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(robots_status, text=robots))
    router.get(f"{SITE}/sitemap.xml").mock(return_value=httpx.Response(404))


async def run(cfg: CrawlConfig, url: str = SITE, clock=None):
    async with httpx.AsyncClient() as client:
        kwargs = {"client": client, "resolver": public_resolver}
        if clock:
            kwargs["clock"] = clock
        return await Crawler(cfg, **kwargs).crawl(url)


# ---------------------------------------------------------------- bad URLs
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("acme.com", "https://acme.com/"),
        ("  https://Acme.com/pricing  ", "https://acme.com/pricing"),
        ("http://acme.com", "http://acme.com/"),
    ],
)
def test_normalize_accepts_common_input(raw, expected):
    assert normalize_start_url(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "   ", "ftp://acme.com", "javascript:alert(1)", "not a url", "https://", "https://acme.com:8443/"]
)
def test_normalize_rejects_bad_urls(raw):
    with pytest.raises(UnsafeUrlError):
        normalize_start_url(raw)


async def test_private_ip_is_refused():
    with pytest.raises(UnsafeUrlError, match="private or internal"):
        await run(config(), "https://internal.acme.test")
    with pytest.raises(UnsafeUrlError):
        await run(config(), "https://loopback.acme.test")


@respx.mock
async def test_redirect_to_internal_host_is_blocked():
    mock_site(respx)
    respx.get(f"{SITE}/").mock(return_value=httpx.Response(302, headers={"location": "http://internal.acme.test/"}))
    result = await run(config())
    assert result.pages == []
    assert "home page could not be fetched" in result.stopped_reason
    assert "private or internal" in result.errors[0][1]


@respx.mock
async def test_home_page_404_reports_error():
    mock_site(respx)
    respx.get(f"{SITE}/").mock(return_value=httpx.Response(404))
    result = await run(config())
    assert result.pages == []
    assert "HTTP 404" in result.stopped_reason


@respx.mock
async def test_timeout_is_recorded_not_raised():
    mock_site(respx)
    respx.get(f"{SITE}/").mock(return_value=page(links("/pricing", "/about")))
    respx.get(f"{SITE}/pricing").mock(side_effect=httpx.ReadTimeout("slow"))
    respx.get(f"{SITE}/about").mock(return_value=page("About us"))
    result = await run(config())
    assert {p.page_type for p in result.pages} == {"home", "about"}
    assert any("timed out" in err for _, err in result.errors)


@respx.mock
async def test_non_html_is_skipped():
    mock_site(respx)
    respx.get(f"{SITE}/").mock(return_value=page(links("/brochure")))
    respx.get(f"{SITE}/brochure").mock(
        return_value=httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
    )
    result = await run(config())
    assert len(result.pages) == 1
    assert any("not HTML" in err for _, err in result.errors)


# ------------------------------------------------------------------ limits
@respx.mock
async def test_page_limit_is_enforced():
    mock_site(respx)
    paths = ["/pricing", "/product", "/features", "/solutions", "/customers", "/about", "/compare", "/use-cases"]
    respx.get(f"{SITE}/").mock(return_value=page(links(*paths)))
    respx.route(method="GET", url__regex=rf"{SITE}/.+").mock(return_value=page("x"))
    result = await run(config(max_pages=5))
    assert len(result.pages) == 6  # home + 5
    assert result.stopped_reason == "page limit reached"


@respx.mock
async def test_per_type_cap_stops_one_section_eating_the_budget():
    mock_site(respx)
    paths = [f"/integrations/tool-{i}" for i in range(40)] + ["/about"]
    respx.get(f"{SITE}/").mock(return_value=page(links(*paths)))
    respx.route(method="GET", url__regex=rf"{SITE}/.+").mock(return_value=page("x"))
    result = await run(config(max_pages=25))
    types = [p.page_type for p in result.pages]
    assert types.count("features") == 4
    assert "about" in types


@respx.mock
async def test_byte_cap_truncates_large_pages():
    mock_site(respx)
    big = "x" * 50_000
    respx.get(f"{SITE}/").mock(return_value=page(big))
    result = await run(config(max_bytes=1_000))
    home = result.pages[0]
    assert home.truncated is True
    assert home.bytes == 1_000


@respx.mock
async def test_time_budget_stops_crawl():
    mock_site(respx)
    respx.get(f"{SITE}/").mock(return_value=page(links("/pricing", "/about", "/product")))
    respx.route(method="GET", url__regex=rf"{SITE}/(pricing|about|product)").mock(return_value=page("x"))
    ticks = iter([0.0])  # crawl starts at t=0; every later reading is past the budget
    result = await run(config(total_budget_seconds=10), clock=lambda: next(ticks, 999.0))
    assert len(result.pages) == 1
    assert result.stopped_reason == "time budget reached"


@respx.mock
async def test_external_and_junk_links_are_not_followed():
    mock_site(respx)
    respx.get(f"{SITE}/").mock(
        return_value=page(
            links("https://other.test/pricing", "/login", "/careers", "/logo.png", "mailto:hi@acme.test", "/pricing")
        )
    )
    respx.get(f"{SITE}/pricing").mock(return_value=page("Pricing $10"))
    result = await run(config())
    assert [p.page_type for p in result.pages] == ["home", "pricing"]
    reasons = dict(result.skipped)
    assert "skipped section 'login'" in reasons.values()
    assert "non-HTML file" in reasons.values()


@respx.mock
async def test_priority_pages_are_fetched_first():
    mock_site(respx)
    respx.get(f"{SITE}/").mock(return_value=page(links("/random-thing", "/blog", "/pricing", "/customers", "/product")))
    respx.route(method="GET", url__regex=rf"{SITE}/.+").mock(return_value=page("x"))
    result = await run(config(max_pages=3, concurrency=1))
    assert [p.page_type for p in result.pages] == ["home", "pricing", "product", "customers"]


# ------------------------------------------------------------------ robots
@respx.mock
async def test_robots_disallowed_paths_are_skipped():
    mock_site(respx, robots="User-agent: *\nDisallow: /pricing\n")
    respx.get(f"{SITE}/").mock(return_value=page(links("/pricing", "/about")))
    respx.get(f"{SITE}/about").mock(return_value=page("About"))
    pricing = respx.get(f"{SITE}/pricing").mock(return_value=page("secret"))
    result = await run(config())
    assert [p.page_type for p in result.pages] == ["home", "about"]
    assert (f"{SITE}/pricing", "blocked by robots.txt") in result.skipped
    assert not pricing.called


@respx.mock
async def test_robots_disallow_all_stops_before_home():
    mock_site(respx, robots="User-agent: *\nDisallow: /\n")
    home = respx.get(f"{SITE}/").mock(return_value=page("hi"))
    result = await run(config())
    assert result.pages == []
    assert "robots.txt" in result.stopped_reason
    assert not home.called


@respx.mock
async def test_robots_specific_to_our_agent_is_respected():
    mock_site(respx, robots="User-agent: GTMStrategyBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    respx.get(f"{SITE}/").mock(return_value=page("hi"))
    result = await run(config(user_agent="GTMStrategyBot/0.1"))
    assert result.pages == []


@respx.mock
async def test_robots_server_error_means_do_not_crawl():
    mock_site(respx, robots="oops", robots_status=503)
    home = respx.get(f"{SITE}/").mock(return_value=page("hi"))
    result = await run(config())
    assert result.pages == [] and not home.called
    assert "503" in result.robots_note


@respx.mock
async def test_missing_robots_allows_crawl():
    mock_site(respx, robots=None)
    respx.get(f"{SITE}/").mock(return_value=page("Welcome to Acme"))
    result = await run(config())
    assert len(result.pages) == 1
    assert "Welcome to Acme" in result.pages[0].text


@respx.mock
async def test_sitemap_urls_are_used():
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(200, text=f"Sitemap: {SITE}/sm.xml\n"))
    respx.get(f"{SITE}/sm.xml").mock(
        return_value=httpx.Response(
            200,
            text='<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{SITE}/pricing</loc></url><url><loc>https://elsewhere.test/x</loc></url></urlset>",
        )
    )
    respx.get(f"{SITE}/").mock(return_value=page("no links here"))
    respx.get(f"{SITE}/pricing").mock(return_value=page("Plans from $49"))
    result = await run(config())
    assert [p.page_type for p in result.pages] == ["home", "pricing"]


@respx.mock
async def test_fetch_single_page_respects_robots():
    mock_site(respx, robots="User-agent: *\nDisallow: /private\n")
    respx.get(f"{SITE}/private").mock(return_value=page("x"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="robots"):
            await fetch_single_page(f"{SITE}/private", config(), client=client, resolver=public_resolver)


# ----------------------------------------------------------- prioritisation
@pytest.mark.parametrize(
    "url, page_type",
    [
        ("https://a.test/", "home"),
        ("https://a.test/pricing", "pricing"),
        ("https://a.test/product/overview", "product"),
        ("https://a.test/customers/acme-story", "customers"),
        ("https://a.test/acme-vs-hubspot", "compare"),
        ("https://a.test/solutions/for-banks", "solutions"),
        ("https://a.test/some-page", "other"),
        ("https://a.test/changelog/2020-zapier-integration", "blog"),
    ],
)
def test_classify(url, page_type):
    assert classify(url)[0] == page_type


def test_should_skip_locale_duplicates_and_app_pages():
    assert should_skip("https://a.test/de/preise") == "other-language duplicate"
    assert should_skip("https://a.test/settings/plans") == "skipped section 'settings'"
    assert should_skip("https://a.test/pricing") is None


def test_top_level_section_beats_deep_keyword():
    assert classify("https://a.test/pricing")[1] > classify("https://a.test/changelog/new-pricing")[1]
    assert classify("https://a.test/customers")[1] > classify("https://a.test/blog/customers-love-us")[1]
