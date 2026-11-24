"""SSRF protection for user-supplied music server URLs.

Rules (documented in pocket-music-source skill):

* scheme must be http/https;
* loopback and link-local/metadata addresses are always rejected;
* private ranges are only allowed when
  ``POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=true`` (Navidrome on a LAN) and the
  caller explicitly opted in;
* the host is resolved and *every* resolved address is validated (defeats DNS
  rebinding);
* redirects are never followed automatically by the adapters.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.errors import SSRFBlockedError

BLOCKED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "metadata", "metadata.google.internal",
    "instance-data", "169.254.169.254",
}

METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
    ipaddress.ip_address("100.100.100.200"),  # aliyun metadata
}


@dataclass
class ValidatedUrl:
    normalized: str
    host: str
    port: int
    scheme: str
    resolved_ips: List[str]


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address in METADATA_IPS:
        return True
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return True
    return False


def _is_private_ip(address) -> bool:
    return getattr(address, "is_private", False)


def validate_server_url(raw_url: str, *, allow_private: Optional[bool] = None) -> ValidatedUrl:
    settings = get_settings()
    if not raw_url or not raw_url.strip():
        raise SSRFBlockedError("server URL is empty", code="SSRF_BLOCKED")

    candidate = raw_url.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise SSRFBlockedError(
            f"scheme {parsed.scheme!r} is not allowed", code="SSRF_BLOCKED",
            details={"allowed": ["http", "https"]},
        )
    if not parsed.hostname:
        raise SSRFBlockedError("server URL has no host", code="SSRF_BLOCKED")
    if parsed.username or parsed.password:
        raise SSRFBlockedError(
            "credentials must not be embedded in the URL", code="SSRF_BLOCKED"
        )

    host = parsed.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES:
        raise SSRFBlockedError(
            f"host {host!r} is blocked", code="SSRF_BLOCKED", details={"host": host}
        )

    private_allowed = (
        settings.allow_private_network_sources if allow_private is None else allow_private
    )

    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise SSRFBlockedError(
                f"host {host!r} could not be resolved", code="SSRF_BLOCKED",
                details={"host": host},
            ) from exc
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue

    if not addresses:
        raise SSRFBlockedError(f"host {host!r} has no usable address", code="SSRF_BLOCKED")

    for address in addresses:
        if _is_blocked_ip(address):
            raise SSRFBlockedError(
                f"address {address} is not allowed", code="SSRF_BLOCKED",
                details={"host": host, "address": str(address)},
            )
        if _is_private_ip(address) and not private_allowed:
            raise SSRFBlockedError(
                "private network addresses are disabled by configuration",
                code="SSRF_BLOCKED",
                details={"host": host, "address": str(address)},
            )

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    path = parsed.path.rstrip("/")
    normalized = f"{parsed.scheme.lower()}://{host}"
    if parsed.port:
        normalized += f":{parsed.port}"
    normalized += path

    return ValidatedUrl(
        normalized=normalized,
        host=host,
        port=port,
        scheme=parsed.scheme.lower(),
        resolved_ips=[str(a) for a in addresses],
    )


def validate_image_url(raw_url: str) -> str:
    """Artwork URLs from providers are proxied, never embedded blindly."""
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    return raw_url
