"""Bounded HTTPS retrieval helpers for remote-version detection."""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import requests


LOGGER = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
_REDIRECT_CODES = {301, 302, 303, 307, 308}
_SENSITIVE_REDIRECT_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
}


class UnsafeRedirectError(ValueError):
    """Raised when a request leaves the allowed HTTPS boundary."""


def is_safe_https_url(url: str | None) -> bool:
    """Return true only for absolute credential-free HTTPS URLs."""
    if not url:
        return False
    try:
        parsed = urlparse(str(url))
        # Accessing .port validates malformed/out-of-range ports.
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def _origin(url: str) -> tuple[str, str, int] | None:
    """Return a normalized origin tuple for a validated URL."""
    if not is_safe_https_url(url):
        return None
    parsed = urlparse(url)
    return (
        parsed.scheme.lower(),
        (parsed.hostname or "").lower(),
        parsed.port or 443,
    )


def _bounded_body(response, max_bytes: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            parsed_length = int(content_length)
        except (TypeError, ValueError):
            LOGGER.debug(
                "Ignoring invalid Content-Length %r", content_length
            )
        else:
            if parsed_length > max_bytes:
                raise ValueError(
                    f"Content-Length {content_length} exceeds "
                    f"{max_bytes} bytes"
                )

    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        remaining = max_bytes - total
        if remaining <= 0 or len(chunk) > remaining:
            raise ValueError(f"response exceeds {max_bytes} bytes")
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _strip_cross_origin_headers(headers: dict, source: str, target: str) -> None:
    """Drop caller-supplied secrets before following a cross-origin redirect."""
    if _origin(source) == _origin(target):
        return
    for key in list(headers):
        if key.lower() in _SENSITIVE_REDIRECT_HEADERS:
            headers.pop(key, None)


def safe_get(
    url: str,
    *,
    timeout: float = 5,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    session=None,
    **kwargs,
):
    """GET an HTTPS URL with bounded redirects, secrets, and response size."""
    if not is_safe_https_url(url):
        raise UnsafeRedirectError(f"unsafe URL rejected: {url!r}")

    client = session or requests
    current = url
    request_headers = dict(kwargs.pop("headers", None) or {})
    request_params = kwargs.pop("params", None)
    kwargs.pop("allow_redirects", None)

    for redirect_count in range(max_redirects + 1):
        response = client.get(
            current,
            headers=request_headers or None,
            params=request_params,
            timeout=timeout,
            stream=True,
            allow_redirects=False,
            **kwargs,
        )
        try:
            location = (
                response.headers.get("Location")
                if response.status_code in _REDIRECT_CODES
                else None
            )
            if location:
                if redirect_count >= max_redirects:
                    raise UnsafeRedirectError(
                        f"too many redirects while fetching {url!r}"
                    )
                target = urljoin(current, location)
                if not is_safe_https_url(target):
                    raise UnsafeRedirectError(
                        f"unsafe redirect rejected: "
                        f"{current!r} -> {target!r}"
                    )
                _strip_cross_origin_headers(
                    request_headers, current, target
                )
                response.close()
                current = target
                # Redirect Location is now authoritative; avoid re-appending
                # caller params on every hop.
                request_params = None
                continue

            # A 3xx without Location is still a response body. Consume it
            # through the same cap rather than returning an unbounded stream.
            body = _bounded_body(response, max_bytes)
            response._content = body
            response._content_consumed = True
            response.url = current
            response.close()
            return response
        except Exception:
            response.close()
            raise

    raise UnsafeRedirectError(f"redirect limit exceeded for {url!r}")
