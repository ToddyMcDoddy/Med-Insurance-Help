import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.contract import PlanTerms, Sourced
from app.upload_rate_limit import UploadRateLimiter

PDF_PATH = (
    Path(__file__).parents[2]
    / "data"
    / "synthetic"
    / "plans"
    / "unifiedhealthcare_choice_plus_ppo_2000.pdf"
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "upload_rate_limiter", UploadRateLimiter())
    monkeypatch.setenv("EXTRACTOR_MODE", "gemini")
    with TestClient(main.app) as test_client:
        yield test_client


def post_fixture(client):
    return client.post(
        "/api/upload/plan",
        files={"file": ("renamed-plan.pdf", PDF_PATH.read_bytes(), "application/pdf")},
    )


def plan_terms(*, confirmed=False, missing=False):
    return PlanTerms(
        insurer="UnifiedHealthcare",
        plan_name="Choice Plus PPO 2000",
        deductible=Sourced(value=2000, page=3, quote="Individual deductible $2,000")
        if not missing
        else None,
        out_of_pocket_max=Sourced(value=6000, page=3, quote="Out-of-pocket maximum $6,000"),
        coinsurance_pct=Sourced(value=20, page=4, quote="You pay 20% coinsurance"),
        copay_primary_care=Sourced(value=30, page=5, quote="Primary care $30 copay"),
        copay_specialist=Sourced(value=60, page=5, quote="Specialist $60 copay"),
        copay_er=Sourced(value=350, page=5, quote="Emergency room $350 copay"),
        not_found=["deductible"] if missing else [],
        confirmed=confirmed,
    )


def test_gemini_upload_uses_validated_text_off_event_loop_and_never_confirms(
    client, monkeypatch
):
    event_loop_thread = []
    extractor_thread = []
    captured_pages = []
    original_extract_pages = main.extract_pdf_pages

    def capture_validated_pages(pdf_bytes):
        event_loop_thread.append(threading.get_ident())
        return original_extract_pages(pdf_bytes)

    def fake_extract_from_pages(pages):
        extractor_thread.append(threading.get_ident())
        captured_pages.extend(pages)
        return plan_terms(confirmed=True)

    monkeypatch.setattr(main, "extract_pdf_pages", capture_validated_pages)
    monkeypatch.setattr(main, "extract_plan_terms_from_pages", fake_extract_from_pages)

    response = post_fixture(client)

    assert response.status_code == 200, response.text
    assert response.json()["confirmed"] is False
    assert response.json()["deductible"]["value"] == 2000
    assert len(captured_pages) == 6
    assert "deductible" in captured_pages[2].lower()
    assert extractor_thread[0] != event_loop_thread[0]


def test_gemini_upload_preserves_missing_terms(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "extract_plan_terms_from_pages",
        lambda pages: plan_terms(missing=True),
    )

    response = post_fixture(client)

    assert response.status_code == 200
    assert response.json()["deductible"] is None
    assert response.json()["not_found"] == ["deductible"]
    assert response.json()["confirmed"] is False


def test_missing_gemini_configuration_returns_safe_503(client, monkeypatch):
    def missing_key(_pages):
        raise RuntimeError("GEMINI_API_KEY is not set; fake-secret-must-not-leak")

    monkeypatch.setattr(main, "extract_plan_terms_from_pages", missing_key)

    response = post_fixture(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "GEMINI_API_KEY is not configured on the server."
    assert "fake-secret" not in response.text


def test_gemini_provider_error_returns_safe_502(client, monkeypatch):
    def provider_failure(_pages):
        raise RuntimeError("provider failure with private details")

    monkeypatch.setattr(main, "extract_plan_terms_from_pages", provider_failure)

    response = post_fixture(client)

    assert response.status_code == 502
    assert response.json()["detail"] == "Plan extraction provider request failed."
    assert "private details" not in response.text