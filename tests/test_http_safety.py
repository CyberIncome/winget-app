import pytest

from src.logic.http_safety import UnsafeRedirectError, is_safe_https_url, safe_get


class FakeResponse:
    def __init__(self, status_code=200, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or [b"ok"]
        self._content = b""
        self.url = ""
        self.closed = False

    def iter_content(self, chunk_size=8192):
        yield from self._chunks

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.responses.pop(0)


def test_https_url_validation():
    assert is_safe_https_url("https://example.com/path")
    assert not is_safe_https_url("http://example.com")
    assert not is_safe_https_url("file:///tmp/x")
    assert not is_safe_https_url("https:///missing-host")


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
