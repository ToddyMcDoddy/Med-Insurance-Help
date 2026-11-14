import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contract import Bill, ChatResponse, EstimateResult, PlanTerms, Sourced

MOCK = Path(__file__).parent.parent / "app" / "mock_data"


def test_mock_plan_terms_valid():
    plan = PlanTerms(**json.loads((MOCK / "plan_terms.json").read_text()))
    assert plan.deductible.value == 2000
    assert plan.deductible.page == 3


def test_mock_bill_valid():
    bill = Bill(**json.loads((MOCK / "bill.json").read_text()))
    assert len(bill.items) == 3


def test_sourced_requires_real_page():
    with pytest.raises(ValidationError):
        Sourced(value=100, page=0)


def test_missing_terms_default_to_none_not_guessed():
    plan = PlanTerms(insurer="X", plan_name="Y")
    assert plan.deductible is None
    assert plan.confirmed is False


def test_estimate_is_always_labeled_estimate():
    with pytest.raises(ValidationError):
        EstimateResult(steps=[], member_pays=0, plan_pays=0, is_estimate=False)


def test_chat_message_length_capped():
    from app.contract import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(session_id="s", message="x" * 2001)


def test_chat_response_defaults():
    r = ChatResponse(answer="hi")
    assert r.refused is False and r.citations == []
