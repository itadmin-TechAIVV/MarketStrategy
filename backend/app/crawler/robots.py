"""robots.txt handling.

Rules (same as major search engines):
- 2xx: parse and obey.
- 404 / other 4xx: no restrictions.
- 401 / 403: treat the whole site as disallowed.
- 5xx or network failure: treat the whole site as disallowed (we can't know the rules).
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


async def fetch_robots(client: httpx.AsyncClient, origin: str, timeout: float) -> RobotsPolicy:
    url = origin.rstrip("/") + "/robots.txt"
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        return RobotsPolicy(disallow_all=True, reason=f"robots.txt unreachable ({type(exc).__name__})")
    if resp.status_code in (401, 403):
        return RobotsPolicy(disallow_all=True, reason=f"robots.txt returned {resp.status_code}")
    if resp.status_code >= 500:
        return RobotsPolicy(disallow_all=True, reason=f"robots.txt returned {resp.status_code}")
    if resp.status_code >= 400:
        return RobotsPolicy(allow_all=True, reason="no robots.txt")
    return parse_robots(resp.text[:MAX_ROBOTS_BYTES])
