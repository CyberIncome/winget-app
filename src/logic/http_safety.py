"""Bounded HTTPS retrieval helpers for remote-version detection."""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import requests


LOGGER = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class UnsafeRedirectError(ValueError):
    """Raised when a redirect leaves the allowed HTTPS boundary."""


def is_safe_https_url(url: str | None) -> bool:
    """Return true only for absolute HTTPS URLs with a hostname."""
    if not url:
        return False
    try:
        parsed = urlparse(str(url))
    except ValueError:
        return False
    return parsed.scheme.lower() == "https" and bool(parsed.hostname)


def _bounded_body(response, max_bytes: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ValueError(
                    f"Content-Length {content_length} exceeds {max_bytes} bytes"
                )
        except ValueError as exc:
            if str(exc).startswith("Content-Length"):
                raise
            LOGGER.debug(
                "Ignoring invalid Content-Length %r", content_length
            )

    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        remaining = max_bytes - total
        if remaining <= 0:
            raise ValueError(f"response exceeds {max_bytes} bytes")
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            raise ValueError(f"response exceeds {max_bytes} bytes")
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def safe_get(
    url: str,
    *,
    timeout: float = 5,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    session=None,
    **kwargs,
):
    """GET an HTTPS URL with bounded redirects and response size."""
    if not is_safe_https_url(url):
        raise UnsafeRedirectError(f"unsafe URL rejected: {url!r}")

    client = session or requests
    current = url
    headers = kwargs.pop("headers", None)
    params = kwargs.pop("params", None)
    kwargs.pop("allow_redirects", None)

    for redirect_count in range(max_redirects + 1):
        response = client.get(
            current,
            headers=headers,
            params=params,
            timeout=timeout,
            stream=True,
            allow_redirects=False,
            **kwargs,
        )
        try:
            if response.status_code in _REDIRECT_CODES:
                location = response.headers.get("Location")
                if not location:
                    return response
                if redirect_count >= max_redirects:
                    raise UnsafeRedirectError(
                        f"too many redirects while fetching {url!r}"
                    )
                target = urljoin(current, location)
                if not is_safe_https_url(target):
                    raise UnsafeRedirectError(
                        f"unsafe redirect rejected: {current!r} -> {target!r}"
                    )
                response.close()
                current = target
                continue

            body = _bounded_body(response, max_bytes)
            response._content = body
            response.url = current
            response.close()
            return response
        except Exception:
            response.close()
            raise

    raise UnsafeRedirectError(f"redirect limit exceeded for {url!r}")
