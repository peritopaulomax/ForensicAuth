"""Helpers for HTTP client identity (behind nginx proxy)."""

from fastapi import Request


def client_ip_from_request(request: Request) -> str:
    """Prefer first X-Forwarded-For hop (nginx), else direct peer."""
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For"
    )
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
