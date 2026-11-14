from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from app import main
from app.main import app
from app.upload_rate_limit import UploadRateLimiter

PLANS_DIR = Path(__file__).parents[2] / "data" / "synthetic" / "plans"


@pytest.fixture(autouse=True)
def reset_upload_rate_limiter(monkeypatch):
    monkeypatch.setattr(main, "upload_rate_limiter", UploadRateLimiter())


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("fixture_name", "plan_name"),
    [
        ("unifiedhealthcare_choice_plus_ppo_2000.pdf", "Choice Plus PPO 2000"),
        ("pvs_healthsaver_hsa_5500.pdf", "HealthSaver HSA 5500"),
        ("advavate_gold_ppo_25_1000_10.pdf", "Gold PPO 25/1000/10%"),
        ("unifiedhealthcare_injected.pdf", "Choice Plus PPO 2000"),
    ],
)
def test_known_demo_pdf_returns_unconfirmed_fixture_plan(
    client, monkeypatch, fixture_name, plan_name
):
    monkeypatch.setenv("EXTRACTOR_MODE", "demo")
    pdf_bytes = (PLANS_DIR / fixture_name).read_bytes()
    response = client.post(
        "/api/upload/plan",
        files={"file": ("not-the-fixture-name.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["X-MediFit-Extraction-Mode"] == "demo"
    plan = response.json()
    assert plan["plan_name"] == plan_name
    assert plan["confirmed"] is False
    for term in plan.values():
        if isinstance(term, dict) and "value" in term:
            assert term["quote"] == ""


def test_demo_missing_terms_remain_null_and_not_found(client, monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODE", "demo")
    pdf_bytes = (PLANS_DIR / "pvs_healthsaver_hsa_5500.pdf").read_bytes()
    response = client.post(
        "/api/upload/plan",
        files={"file": ("pvs.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["out_of_pocket_max"] is None
    assert plan["copay_primary_care"] is None
    assert plan["copay_specialist"] is None
    assert plan["copay_er"] is None
    assert plan["not_found"] == [
        "out_of_pocket_max",
        "copay_primary_care",
        "copay_specialist",
        "copay_er",
    ]


def test_unknown_valid_pdf_is_rejected_even_with_known_fixture_filename(
    client, monkeypatch
):
    monkeypatch.setenv("EXTRACTOR_MODE", "demo")
    source = PdfReader(str(PLANS_DIR / "unifiedhealthcare_choice_plus_ppo_2000.pdf"))
    writer = PdfWriter(clone_from=source)
    writer.add_metadata({"/Subject": "Different synthetic document"})
    output = BytesIO()
    writer.write(output)
    response = client.post(
        "/api/upload/plan",
        files={
            "file": (
                "unifiedhealthcare_choice_plus_ppo_2000.pdf",
                output.getvalue(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert "not one of the bundled synthetic demo fixtures" in response.json()["detail"]


def test_demo_disabled_keeps_501_response(client, monkeypatch):
    monkeypatch.delenv("EXTRACTOR_MODE", raising=False)
    pdf_bytes = (PLANS_DIR / "unifiedhealthcare_choice_plus_ppo_2000.pdf").read_bytes()
    response = client.post(
        "/api/upload/plan",
        files={"file": ("plan.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 501
    assert response.json()["detail"] == "Plan extraction is not connected yet."
    assert "X-MediFit-Extraction-Mode" not in response.headers