"""Resolve client IPs without blindly trusting forwarded headers."""
from __future__ import annotations

import ipaddress

from fastapi import Request


_TRUSTED_PROXY_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
    )
)


def _parse_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(request: Request) -> str | None:
    peer = _parse_ip(request.client.host if request.client else None)
    if peer is None:
        return None

    peer_address = ipaddress.ip_address(peer)
    if any(peer_address in network for network in _TRUSTED_PROXY_NETWORKS):
        forwarded = request.headers.get("x-forwarded-for", "")
        for candidate in forwarded.split(","):
            parsed = _parse_ip(candidate)
            if parsed is not None:
                return parsed[:45]
    return peer[:45]
