"""Turn raw HTML into clean text, a title, links and image alt texts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:  # trafilatura is the preferred extractor; BeautifulSoup is the fallback.
    import trafilatura
except Exception:  # pragma: no cover - optional at import time
    trafilatura = None

MAX_TEXT_CHARS = 50_000
MAX_STRUCTURED_CHARS = 4_000

# JSON-LD keys worth keeping (product, pricing, organisation, FAQ facts).
LD_KEYS = (
    "@type", "name", "alternateName", "description", "slogan", "url", "brand", "category", "applicationCategory",
    "operatingSystem", "offers", "price", "priceCurrency", "lowPrice", "highPrice", "priceSpecification",
    "billingDuration", "unitText", "aggregateRating", "ratingValue", "reviewCount", "foundingDate", "founder",
    "numberOfEmployees", "address", "addressCountry", "addressLocality", "areaServed", "audience", "audienceType",
    "mainEntity", "acceptedAnswer", "text", "sameAs", "feature", "featureList", "award", "knowsAbout",
)
LD_SKIP_TYPES = {"BreadcrumbList", "WebSite", "SearchAction", "ImageObject", "WebPage", "SiteNavigationElement", "ReadAction"}


@dataclass
class Extracted:
    title: str = ""
    description: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    image_alts: list[str] = field(default_factory=list)
    body_chars: int = 0  # visible page text only, without the structured-data summary


def _fallback_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    lines = [ln.strip() for ln in root.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _ld_lines(node, depth: int = 0, out: list[str] | None = None) -> list[str]:
    """Flatten the useful parts of a JSON-LD object into readable lines."""
    out = [] if out is None else out
    if depth > 5 or len(out) > 200:
        return out
    if isinstance(node, list):
        for item in node:
            _ld_lines(item, depth, out)
        return out
    if not isinstance(node, dict):
        return out
    if "@graph" in node:
        _ld_lines(node["@graph"], depth, out)
    types_ = node.get("@type")
    type_list = types_ if isinstance(types_, list) else [types_]
    if any(t in LD_SKIP_TYPES for t in type_list if isinstance(t, str)):
        return out
    indent = "  " * depth
    for key in LD_KEYS:
        if key not in node:
            continue
        val = node[key]
        if isinstance(val, (str, int, float)) and str(val).strip():
            sval = " ".join(str(val).split())
            if key == "@type":
                out.append(f"{indent}[{sval}]")
            elif len(sval) <= 600:
                out.append(f"{indent}{key}: {sval}")
        elif isinstance(val, list) and val and all(isinstance(v, str) for v in val):
            out.append(f"{indent}{key}: {', '.join(v for v in val[:15])}")
        elif isinstance(val, (dict, list)):
            out.append(f"{indent}{key}:")
            _ld_lines(val, depth + 1, out)
    return out


def structured_data_text(soup: BeautifulSoup) -> str:
    """Readable summary of JSON-LD and Open Graph metadata. JavaScript-built sites often
    put their product, pricing and organisation facts here even when the body is empty."""
    lines: list[str] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        lines.extend(_ld_lines(data))
    meta = []
    for prop in ("og:site_name", "og:title", "og:description", "twitter:description"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            meta.append(f"{prop}: {' '.join(tag['content'].split())}")
    text = ""
    if lines:
        text += "Structured data on this page:\n" + "\n".join(lines)
    if meta:
        text += ("\n" if text else "") + "Page metadata:\n" + "\n".join(meta)
    return text[:MAX_STRUCTURED_CHARS]


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

    structured = structured_data_text(soup)  # read before the fallback strips <script> tags

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
    out.body_chars = len(text)
    if structured:
        text = f"{text}\n\n{structured}" if text else structured
    out.text = text[:MAX_TEXT_CHARS]
    return out


_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def markdown_to_text(markdown: str) -> tuple[str, list[str]]:
    """Plain text from the reader's markdown: images become their alt text, links their label."""
    alts: list[str] = []
    for m in _MD_IMAGE.finditer(markdown):
        alt = " ".join(m.group(1).split())
        if alt.lower().startswith("image "):  # reader placeholder like "Image 3: Acme logo"
            alt = alt.split(":", 1)[-1].strip()
        if 1 < len(alt) <= 60 and alt.lower() not in {a.lower() for a in alts}:
            alts.append(alt)
    text = _MD_IMAGE.sub("", markdown)
    text = _MD_LINK.sub(lambda m: m.group(1), text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    cleaned: list[str] = []
    for ln in lines:
        if ln.strip() or (cleaned and cleaned[-1].strip()):
            cleaned.append(ln)
    return "\n".join(cleaned).strip(), alts
