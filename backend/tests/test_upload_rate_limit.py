from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.upload_rate_limit import UploadRateLimiter

PDF_PATH = (
    Path(__file__).parents[2]
    / "data"
    / "synthetic"
    / "plans"
    / "unifiedhealthcare_choice_plus_ppo_2000.pdf"
)


@pytest.fixture
def fake_clock_and_limiter(monkeypatch):
    now = [1000.0]
    limiter = UploadRateLimiter(clock=lambda: now[0])
    monkeypatch.setattr(main, "upload_rate_limiter", limiter)
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    monkeypatch.delenv("EXTRACTOR_MODE", raising=False)
    return now, limiter


def upload(client, pdf_bytes, *, headers=None):
    return client.post(
        "/api/upload/plan",
        files={"file": ("plan.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )


def test_rate_limit_rejects_before_parsing_and_recovers(fake_clock_and_limiter):
    now, _ = fake_clock_and_limiter
    pdf_bytes = PDF_PATH.read_bytes()
    with TestClient(app) as client:
        first = upload(client, pdf_bytes)
        assert first.status_code == 501

        blocked = upload(
            client,
            b"not a PDF",
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "60"
        assert "rate limit" in blocked.json()["detail"].lower()

        now[0] += 60
        recovered = upload(client, pdf_bytes)
        assert recovered.status_code == 501


def test_limiter_state_is_bounded():
    now = [50.0]
    limiter = UploadRateLimiter(
        max_clients=1,
        max_events=1,
        clock=lambda: now[0],
    )

    assert limiter.check("client-a", 10) is None
    assert limiter.check("client-b", 10) == 60
    assert len(limiter._events) == 1
    assert limiter._event_count == 1