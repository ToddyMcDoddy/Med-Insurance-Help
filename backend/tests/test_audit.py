"""Tests for all six synthetic bill examples and duplicate grouping."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.audit import audit
from app.contract import Bill, Eob


REPO_ROOT = Path(__file__).resolve().parents[2]
BILLS_DIR = REPO_ROOT / "data" / "synthetic" / "bills"


def _load_case(path: Path):
    data = json.loads(path.read_text())
    bill = Bill.model_validate(data["bill"])
    eob = Eob.model_validate(data["eob"]) if data.get("eob") is not None else None
    expected = {
        (item["kind"], tuple(item["line_ids"]))
        for item in data["expected_flags"]
    }
    return bill, eob, expected


@pytest.mark.parametrize("case_path", sorted(BILLS_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_synthetic_bill_cases(case_path: Path):
    bill, eob, expected = _load_case(case_path)

    result = audit(bill, eob)

    actual = {(flag.kind, tuple(flag.line_ids)) for flag in result.flags}
    assert actual == expected
    assert all("fraud" not in flag.detail.casefold() for flag in result.flags)
    assert all(
        "worth asking about" in flag.detail.casefold()
        for flag in result.flags
    )


def test_three_identical_lines_are_grouped_into_one_flag():
    bill = Bill.model_validate(
        {
            "bill_id": "BILL-THREE",
            "items": [
                {
                    "line_id": line_id,
                    "provider": "Riverside Imaging",
                    "date_of_service": "2026-03-04",
                    "code": "73721",
                    "description": "MRI knee without contrast",
                    "amount": 1200.0,
                }
                for line_id in ("L1", "L2", "L3")
            ],
        }
    )

    result = audit(bill)

    exact_flags = [flag for flag in result.flags if flag.kind == "exact_duplicate"]
    assert len(exact_flags) == 1
    assert exact_flags[0].line_ids == ["L1", "L2", "L3"]


def test_different_codes_on_same_date_are_not_same_service_twice():
    bill = Bill.model_validate(
        {
            "bill_id": "BILL-DIFFERENT-CODES",
            "items": [
                {
                    "line_id": "L1",
                    "provider": "Cedar Lab",
                    "date_of_service": "2026-08-14",
                    "code": "80053",
                    "description": "Comprehensive metabolic panel",
                    "amount": 18.0,
                },
                {
                    "line_id": "L2",
                    "provider": "Cedar Lab",
                    "date_of_service": "2026-08-14",
                    "code": "36415",
                    "description": "Blood draw",
                    "amount": 4.0,
                },
            ],
        }
    )

    result = audit(bill)

    assert not any(flag.kind == "same_service_twice" for flag in result.flags)
