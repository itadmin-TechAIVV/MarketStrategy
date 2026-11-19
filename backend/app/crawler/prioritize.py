"""Decide which internal pages are worth crawling first.

Pages are classified by their top-level path segment (`/pricing`, `/customers/...`).
A keyword found only deeper in the path (`/changelog/zapier-integration`) counts
for much less. Each page type has a cap so one big section (integrations,
changelog, blog) can't use up the whole page budget.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# (page_type, score, path keywords). First match wins, so order matters.
PAGE_TYPES: list[tuple[str, int, tuple[str, ...]]] = [
    ("pricing", 100, ("pricing", "prices", "plans")),
    ("product", 90, ("product", "products", "platform", "how-it-works", "overview", "tour", "plan")),
    ("features", 85, ("features", "feature", "capabilities", "integrations")),
    ("solutions", 80, ("solutions", "solution", "industries", "industry", "for-")),
    ("use_cases", 75, ("use-cases", "use-case", "usecases", "teams", "roles")),
    ("customers", 72, ("customers", "customer", "case-studies", "case-study", "stories", "testimonials", "success-stories")),
    ("compare", 70, ("compare", "comparison", "vs", "alternative", "alternatives", "switch")),
    ("about", 60, ("about", "company", "about-us", "mission")),
    ("security", 45, ("security", "trust", "compliance")),
    ("blog", 30, ("blog", "news", "insights", "resources", "articles", "changelog", "now", "updates", "press")),
    ("docs", 20, ("docs", "documentation", "help", "support", "faq", "guides")),
]

# Max pages per type (home is always 1). Anything not listed: 3.
TYPE_CAPS = {
    "pricing": 2, "product": 5, "features": 4, "solutions": 4, "use_cases": 3, "customers": 3,
    "compare": 3, "about": 2, "security": 1, "blog": 3, "docs": 1, "other": 3,
}

SKIP_KEYWORDS = (
    "login", "log-in", "signin", "sign-in", "signup", "sign-up", "register", "logout", "cart", "checkout",
    "account", "settings", "dashboard", "app", "careers", "jobs", "privacy", "terms", "legal", "cookie",
    "cookies", "gdpr", "imprint", "sitemap", "wp-admin", "wp-login", "feed", "rss", "tag", "tags", "author",
    "page", "download", "downloads", "status",
)
SKIP_EXTENSIONS = re.compile(
    r"\.(pdf|jpe?g|png|gif|svg|webp|ico|mp4|mov|avi|webm|mp3|wav|zip|gz|tar|rar|7z|exe|dmg|css|js|json|xml|txt|woff2?|ttf|eot|csv|xlsx?|docx?|pptx?)$",
    re.I,
)
LOCALE_PREFIX = re.compile(r"^/[a-z]{2}(?:[-_][a-zA-Z]{2})?(?:/|$)")
NOT_LOCALES = {"ai", "hr", "it", "io", "go", "us", "my", "vs", "do", "me", "up"}


def _segments(path: str) -> list[str]:
    return [s for s in path.lower().split("/") if s]


def _match(seg: str, keywords: tuple[str, ...]) -> bool:
    for kw in keywords:
        if kw.endswith("-"):
            if seg.startswith(kw):
                return True
        elif seg == kw or seg.startswith(kw + "-"):
            return True
    return False


def classify(url: str) -> tuple[str, int]:
    """Return (page_type, score). Higher score = crawl sooner."""
    segs = _segments(urlsplit(url).path or "/")
    if not segs:
        return "home", 1000
    depth_penalty = 6 * (len(segs) - 1)
    if any("-vs-" in seg or seg.startswith("vs-") for seg in segs):
        return "compare", 70 - depth_penalty
    for page_type, score, keywords in PAGE_TYPES:
        if _match(segs[0], keywords):
            return page_type, score - depth_penalty
    # Keyword only deeper in the path: weak signal.
    for page_type, score, keywords in PAGE_TYPES:
        if any(_match(seg, keywords) for seg in segs[1:]):
            return page_type, max(1, score - 40 - depth_penalty)
    return "other", 10 - len(segs)


def should_skip(url: str, home_is_localized: bool = False) -> str | None:
    """Return a reason string if the URL should not be crawled, else None."""
    path = urlsplit(url).path or "/"
    if SKIP_EXTENSIONS.search(path):
        return "non-HTML file"
    segs = _segments(path)
    for seg in segs:
        if seg in SKIP_KEYWORDS:
            return f"skipped section '{seg}'"
    if not home_is_localized and segs and LOCALE_PREFIX.match(path) and len(segs[0]) in (2, 5):
        if segs[0] not in NOT_LOCALES:
            return "other-language duplicate"
    return None
