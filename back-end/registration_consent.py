"""FR-1.3: store a versioned consent decision with server-recorded metadata.

The peer IP is authoritative. Only opt in to trusting a reverse proxy after
configuring its *specific* address/CIDR via REGISTRATION_TRUSTED_PROXY_CIDRS.
Otherwise an attacker could forge X-Real-IP directly to the API.
"""

from datetime import datetime, timezone
import ipaddress
import os

PRIVACY_NOTICE_VERSION = "2026-10-28-v1"


def client_ip_from_request(request) -> str:
    peer = request.client.host if request.client else None
    if not peer:
        return "unknown"
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return "unknown"

    trusted_cidrs = os.environ.get("REGISTRATION_TRUSTED_PROXY_CIDRS", "")
    for cidr in trusted_cidrs.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            if peer_address in ipaddress.ip_network(cidr, strict=False):
                # Nginx overwrites X-Real-IP; do not take X-Forwarded-For from
                # arbitrary clients. Only accept a syntactically valid address.
                header_value = request.headers.get("x-real-ip", "").strip()
                if header_value:
                    return str(ipaddress.ip_address(header_value))
        except ValueError:
            continue
    return str(peer_address)


def consent_details(request) -> dict:
    return {
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        "consented_at": datetime.now(timezone.utc),
        "ip_address": client_ip_from_request(request),
    }
