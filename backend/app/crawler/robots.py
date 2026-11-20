"""robots.txt handling.

Rules:
- 2xx: parse and obey (including rules aimed at our crawler by name).
- Any 4xx, including 401/403: no robots.txt rules apply (Google treats 4xx the same way).
  Firewalls often answer 403 to non-browser requests even when the site allows crawling.
- 5xx or network failure: the rules can't be read; crawl conservatively (the crawl is
  user-initiated, single-site and capped at a few dozen pages) and record a note.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

import httpx

MAX_ROBOTS_BYTES = 500_000


@dataclass
class RobotsPolicy:
    allow_all: bool = False
    disallow_all: bool = False
    reason: str = ""
    parser: RobotFileParser | None = None
    sitemaps: list[str] = field(default_factory=list)

    def allowed(self, url: str, user_agent: str) -> bool:
        if self.disallow_all:
            return False
        if self.allow_all or self.parser is None:
            return True
        return self.parser.can_fetch(user_agent, url)


def parse_robots(text: str) -> RobotsPolicy:
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lower().startswith("sitemap:") and ":" in line
    ]
    return RobotsPolicy(parser=parser, sitemaps=sitemaps)


async def fetch_robots(
    client: httpx.AsyncClient, origin: str, timeout: float, headers: dict[str, str] | None = None
) -> RobotsPolicy:
    url = origin.rstrip("/") + "/robots.txt"
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True, headers=headers)
    except httpx.HTTPError as exc:
        return RobotsPolicy(allow_all=True, reason=f"robots.txt unreachable ({type(exc).__name__}); crawling conservatively")
    if resp.status_code >= 500:
        return RobotsPolicy(allow_all=True, reason=f"robots.txt returned {resp.status_code}; crawling conservatively")
    if resp.status_code >= 400:
        return RobotsPolicy(allow_all=True, reason=f"no robots.txt rules ({resp.status_code})")
    ctype = resp.headers.get("content-type", "").lower()
    if "html" in ctype:  # some sites serve their home page or an error page at /robots.txt
        return RobotsPolicy(allow_all=True, reason="robots.txt is not a rules file")
    return parse_robots(resp.text[:MAX_ROBOTS_BYTES])
