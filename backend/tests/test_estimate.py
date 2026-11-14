import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

DATA = Path(__file__).parents[2] / "data" / "synthetic"
CASES = json.loads((DATA / "estimate_cases.json").read_text())
EXPECTED_TERMS = json.loads((DATA / "plans" / "expected_terms.json").read_text())


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def request_for(case, *, confirmed=True):
    plan_data = EXPECTED_TERMS[case["plan_file"]]
    plan = {
        "insurer": plan_data["insurer"],
        "plan_name": plan_data["plan_name"],
        **plan_data["terms"],
        "not_found": plan_data["not_found"],
        "confirmed": confirmed,
    }
    return {
        "plan": plan,
        "progress": {
            "deductible_met": case["deductible_met"],
            "out_of_pocket_so_far": case["out_of_pocket_so_far"],
        },
        "service": case["service"],
        "allowed_amount": case["allowed_amount"],
        "kind": case["kind"],
        "copay_type": case["copay_type"],
    }


def post_estimate(client, payload):
    body = json.dumps(payload, allow_nan=True)
    return client.post(
        "/api/estimate",
        content=body,
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_synthetic_estimate_cases(client, case):
    response = client.post("/api/estimate", json=request_for(case))
    expected = case["expected"]

    if expected["member_pays"] is None:
        assert response.status_code == 400
        detail = response.json()["detail"]
        for missing_term in expected["missing"]:
            assert missing_term in detail
        assert "Traceback" not in detail
        return

    assert response.status_code == 200
    result = response.json()
    assert result["member_pays"] == pytest.approx(expected["member_pays"])
    assert result["plan_pays"] == pytest.approx(expected["plan_pays"])
    assert result["missing"] == expected["missing"]
    assert result["is_estimate"] is True
    assert result["disclaimer"]
    assert result["steps"]
    assert all(step["source_page"] is not None for step in result["steps"])


def test_unconfirmed_plan_returns_clear_400(client):
    case = next(case for case in CASES if case["id"] == "uh-02")
    response = client.post("/api/estimate", json=request_for(case, confirmed=False))

    assert response.status_code == 400
    assert "confirmed" in response.json()["detail"].lower()
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    ("case_id", "missing_terms"),
    [
        ("pvs-01", ["out_of_pocket_max"]),
        ("pvs-02", ["copay_primary_care", "out_of_pocket_max"]),
    ],
)
def test_missing_required_terms_return_clear_400(client, case_id, missing_terms):
    case = next(case for case in CASES if case["id"] == case_id)
    response = client.post("/api/estimate", json=request_for(case))

    assert response.status_code == 400
    detail = response.json()["detail"]
    for missing_term in missing_terms:
        assert missing_term in detail
    assert "Traceback" not in detail


@pytest.mark.parametrize("allowed_amount", [-1, float("nan"), float("inf"), -float("inf")])
def test_invalid_allowed_amount_returns_safe_422(client, allowed_amount):
    case = next(case for case in CASES if case["id"] == "uh-02")
    payload = request_for(case)
    payload["allowed_amount"] = allowed_amount

    response = post_estimate(client, payload)

    assert response.status_code == 422
    assert response.json()["detail"]
    assert "Traceback" not in response.text


@pytest.mark.parametrize("percentage", [-1, 100.1, 101])
def test_invalid_coinsurance_percentage_returns_safe_422(client, percentage):
    case = next(case for case in CASES if case["id"] == "uh-02")
    payload = request_for(case)
    payload["plan"]["coinsurance_pct"]["value"] = percentage

    response = post_estimate(client, payload)

    assert response.status_code == 422
    assert response.json()["detail"]
    assert "Traceback" not in response.text


@pytest.mark.parametrize("progress_value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_progress_returns_safe_422(client, progress_value):
    case = next(case for case in CASES if case["id"] == "uh-02")
    payload = request_for(case)
    payload["progress"]["out_of_pocket_so_far"] = progress_value

    response = post_estimate(client, payload)

    assert response.status_code == 422
    assert response.json()["detail"]
    assert "Traceback" not in response.text