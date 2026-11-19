"""Turn raw HTML into clean text, a title, links and image alt texts."""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:  # trafilatura is the preferred extractor; BeautifulSoup is the fallback.
    import trafilatura
except Exception:  # pragma: no cover - optional at import time
    trafilatura = None

MAX_TEXT_CHARS = 50_000


@dataclass
class Extracted:
    title: str = ""
    description: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    image_alts: list[str] = field(default_factory=list)


def _fallback_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    lines = [ln.strip() for ln in root.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract(html: str, base_url: str) -> Extracted:
    soup = BeautifulSoup(html, "lxml")
    out = Extracted()

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if soup.title and soup.title.string:
        out.title = soup.title.string.strip()
    elif og_title and og_title.get("content"):
        out.title = og_title["content"].strip()

    desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if desc and desc.get("content"):
        out.description = desc["content"].strip()

    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            out.links.append(absolute)

    alts: list[str] = []
    for img in soup.find_all("img", alt=True):
        alt = " ".join(img["alt"].split())
        if 1 < len(alt) <= 60 and alt.lower() not in {a.lower() for a in alts}:
            alts.append(alt)
    out.image_alts = alts[:60]

    text = ""
    if trafilatura is not None:
        try:
            text = trafilatura.extract(
                html, url=base_url, include_tables=True, include_comments=False, favor_recall=True
            ) or ""
        except Exception:
            text = ""
    if len(text) < 200:
        fallback = _fallback_text(soup)
        if len(fallback) > len(text):
            text = fallback
    out.text = text[:MAX_TEXT_CHARS]
    return out
