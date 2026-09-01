import pytest

from src.logic.http_safety import (
    UnsafeRedirectError,
    is_safe_https_url,
    safe_get,
)


class FakeResponse:
    def __init__(self, status_code=200, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or [b"ok"]
        self._content = b""
        self._content_consumed = False
        self.url = ""
        self.closed = False

    def iter_content(self, chunk_size=8192):
        yield from self._chunks

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    @property
    def urls(self):
        return [url for url, _kwargs in self.calls]

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_https_url_validation():
    assert is_safe_https_url("https://example.com/path")
    assert not is_safe_https_url("http://example.com")
    assert not is_safe_https_url("file:///tmp/x")
    assert not is_safe_https_url("https:///missing-host")
    assert not is_safe_https_url("https://user:secret@example.com/path")
    assert not is_safe_https_url("https://example.com:99999/path")


def test_rejects_https_to_http_redirect_before_requesting_target():
    session = FakeSession(
        [FakeResponse(302, {"Location": "http://example.com/unsafe"})]
    )
    with pytest.raises(UnsafeRedirectError):
        safe_get("https://example.com/start", session=session)
    assert session.urls == ["https://example.com/start"]


def test_follows_valid_https_redirect():
    session = FakeSession(
        [
            FakeResponse(302, {"Location": "/next"}),
            FakeResponse(200, chunks=[b"hello"]),
        ]
    )
    response = safe_get("https://example.com/start", session=session)
    assert session.urls == [
        "https://example.com/start",
        "https://example.com/next",
    ]
    assert response._content == b"hello"
    assert response._content_consumed is True
    assert response.closed


def test_response_body_cap_fails_closed():
    session = FakeSession(
        [FakeResponse(200, chunks=[b"12345", b"67890"])]
    )
    with pytest.raises(ValueError, match="response exceeds"):
        safe_get(
            "https://example.com/start",
            session=session,
            max_bytes=8,
        )


def test_redirect_without_location_is_still_bounded_and_closed():
    response = FakeResponse(
        302,
        headers={},
        chunks=[b"redirect-body"],
    )
    session = FakeSession([response])
    result = safe_get("https://example.com/start", session=session)
    assert result is response
    assert result._content == b"redirect-body"
    assert result._content_consumed is True
    assert result.closed


def test_cross_origin_redirect_drops_explicit_secrets():
    session = FakeSession(
        [
            FakeResponse(
                302,
                {"Location": "https://cdn.example.net/release"},
            ),
            FakeResponse(200),
        ]
    )
    safe_get(
        "https://api.example.com/start",
        session=session,
        headers={
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "Accept": "application/json",
        },
    )
    second_headers = session.calls[1][1]["headers"]
    assert "Authorization" not in second_headers
    assert "Cookie" not in second_headers
    assert second_headers["Accept"] == "application/json"


def test_cross_origin_redirect_drops_auth_and_cookie_kwargs():
    session = FakeSession(
        [
            FakeResponse(
                302,
                {"Location": "https://cdn.example.net/release"},
            ),
            FakeResponse(200),
        ]
    )
    safe_get(
        "https://api.example.com/start",
        session=session,
        auth=("user", "secret"),
        cookies={"session": "secret"},
    )

    first_kwargs = session.calls[0][1]
    second_kwargs = session.calls[1][1]
    assert first_kwargs["auth"] == ("user", "secret")
    assert first_kwargs["cookies"] == {"session": "secret"}
    assert "auth" not in second_kwargs
    assert "cookies" not in second_kwargs


def test_same_origin_redirect_keeps_authorization():
    session = FakeSession(
        [
            FakeResponse(302, {"Location": "/next"}),
            FakeResponse(200),
        ]
    )
    safe_get(
        "https://api.example.com/start",
        session=session,
        headers={"Authorization": "Bearer secret"},
    )
    assert session.calls[1][1]["headers"]["Authorization"] == (
        "Bearer secret"
    )
