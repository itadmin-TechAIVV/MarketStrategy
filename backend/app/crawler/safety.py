"""URL validation and SSRF protection.

Users type URLs that the *server* fetches, so every URL (including every
redirect hop) must resolve only to public IP addresses.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Awaitable, Callable
from urllib.parse import urldefrag, urlsplit, urlunsplit

Resolver = Callable[[str], Awaitable[list[str]]]

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443}


class UnsafeUrlError(ValueError):
    """The URL is malformed or points somewhere we refuse to fetch."""


async def system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host '{host}'") from exc
    return sorted({info[4][0] for info in infos})


def normalize_start_url(raw: str) -> str:
    """Turn user input like 'acme.com' into 'https://acme.com/'. Raises UnsafeUrlError."""
    raw = (raw or "").strip()
    if not raw:
        raise UnsafeUrlError("No URL given")
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Only http and https URLs are supported (got '{parts.scheme}')")
    host = (parts.hostname or "").lower()
    if not host or "." not in host and host != "localhost":
        raise UnsafeUrlError(f"'{raw}' is not a valid website address")
    if " " in host:
        raise UnsafeUrlError(f"'{raw}' is not a valid website address")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError(f"Invalid port in '{raw}'") from exc
    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError("Only standard web ports (80/443) are allowed")
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def canonical(url: str) -> str:
    """Canonical form used for de-duplication: no fragment, no query, no trailing slash (except root)."""
    url, _ = urldefrag(url)
    parts = urlsplit(url)
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return urlunsplit((parts.scheme.lower(), host, path, "", ""))


def is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


async def assert_public_url(url: str, resolver: Resolver) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Blocked scheme '{parts.scheme}'")
    try:
        if parts.port not in ALLOWED_PORTS:
            raise UnsafeUrlError("Only standard web ports (80/443) are allowed")
    except ValueError as exc:
        raise UnsafeUrlError("Invalid port") from exc
    host = parts.hostname or ""
    if not host:
        raise UnsafeUrlError("URL has no host")
    ips = await resolver(host)
    if not ips:
        raise UnsafeUrlError(f"Could not resolve host '{host}'")
    for ip in ips:
        if not is_public_ip(ip):
            raise UnsafeUrlError(f"'{host}' resolves to a private or internal address; refusing to fetch it")


def same_site(url: str, root_host: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    strip = lambda h: h[4:] if h.startswith("www.") else h  # noqa: E731
    return strip(host) == strip(root_host.lower())
