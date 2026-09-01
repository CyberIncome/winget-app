from src.logic import worker_jobs


class RecordingQueue:
    def __init__(self):
        self.values = []

    def put(self, value):
        self.values.append(value)


class FakeResponse:
    status_code = 200

    def json(self):
        return {"resources": {"core": {"remaining": 42, "limit": 60}}}


def test_worker_serializes_success():
    queue = RecordingQueue()
    worker_jobs._run_worker(queue, lambda: {"value": 7})
    assert queue.values == [{"ok": True, "value": {"value": 7}}]


def test_worker_serializes_failure_with_traceback():
    queue = RecordingQueue()

    def fail():
        raise RuntimeError("boom")

    worker_jobs._run_worker(queue, fail)
    envelope = queue.values[0]
    assert envelope["ok"] is False
    assert envelope["error_type"] == "RuntimeError"
    assert envelope["error"] == "boom"
    assert "RuntimeError: boom" in envelope["traceback"]


def test_github_worker_uses_hardened_transport(monkeypatch):
    queue = RecordingQueue()
    calls = []

    def fake_safe_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(
        "src.logic.http_safety.safe_get", fake_safe_get
    )
    worker_jobs.github_rate_limit_worker("secret", queue)

    assert calls[0][0] == "https://api.github.com/rate_limit"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"
    assert queue.values[0]["ok"] is True
    assert queue.values[0]["value"]["status_code"] == 200
