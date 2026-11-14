import pytest
from fastapi.testclient import TestClient

from app import main
from app.chat_service import (
    AUDIT_UNAVAILABLE_REPLY,
    ChatSessionLimitError,
    ChatSessionStore,
    ChatTurnLimitError,
    GeminiProviderError,
    ModelReply,
    ToolCall,
)
from app.contract import NOT_FOUND_REPLY, REFUSAL_REPLY


class FakeGeminiAdapter:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate(
        self,
        messages,
        *,
        system_instruction,
        tool_declarations,
        max_output_tokens,
    ):
        self.calls.append(
            {
                "messages": messages,
                "system_instruction": system_instruction,
                "tool_declarations": tool_declarations,
                "max_output_tokens": max_output_tokens,
            }
        )
        return self.replies.pop(0)


@pytest.fixture

def client(monkeypatch):
    monkeypatch.setattr(main, "chat_sessions", ChatSessionStore())
    with TestClient(main.app) as test_client:
        yield test_client


def context_payload(
    *,
    session_doc_id="plan-doc",
    deductible=1000,
    include_oop=True,
    confirmed=True,
    text="Individual deductible: $1,000. Out-of-pocket maximum: $4,000. You pay 20% coinsurance.",
):
    plan = {
        "insurer": "Synthetic Health",
        "plan_name": "Synthetic PPO",
        "deductible": {"value": deductible, "page": 1, "quote": "Individual deductible"},
        "coinsurance_pct": {"value": 20, "page": 1, "quote": "20% coinsurance"},
        "copay_primary_care": {"value": 30, "page": 1, "quote": "Primary care $30"},
        "copay_specialist": None,
        "copay_er": None,
        "not_found": [],
    }
    if include_oop:
        plan["out_of_pocket_max"] = {
            "value": 4000,
            "page": 1,
            "quote": "Out-of-pocket maximum",
        }
    else:
        plan["out_of_pocket_max"] = None
        plan["not_found"] = ["out_of_pocket_max"]
    return {
        "plan": plan,
        "plan_document_id": session_doc_id,
        "documents": [{"doc_id": session_doc_id, "page": 1, "text": text}],
        "confirmed": confirmed,
    }


def associate_context(client, session_id="session-a", **kwargs):
    response = client.put(
        f"/api/chat/sessions/{session_id}/context",
        json=context_payload(**kwargs),
    )
    assert response.status_code == 200, response.text
    return response


def install_adapter(monkeypatch, *replies):
    adapter = FakeGeminiAdapter(replies)
    monkeypatch.setattr(main, "chat_adapter_factory", lambda: adapter)
    return adapter


def test_estimate_tool_calls_python_calculator_and_returns_citations(client, monkeypatch):
    associate_context(client)
    adapter = install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("estimate_cost", {}, "estimate-1"),)),
        ModelReply(text="The calculator estimates your share at $1,400."),
    )

    response = client.post(
        "/api/chat",
        json={
            "session_id": "session-a",
            "message": "Estimate the cost of my MRI.",
            "estimate_input": {
                "service": "MRI",
                "allowed_amount": 3000,
                "kind": "coinsurance",
            },
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estimate"]["member_pays"] == pytest.approx(1400)
    assert body["estimate"]["plan_pays"] == pytest.approx(1600)
    assert body["citations"] == [{"doc_id": "plan-doc", "page": 1}]
    assert adapter.calls[0]["max_output_tokens"] == 800
    assert "estimate_cost" in [tool["name"] for tool in adapter.calls[0]["tool_declarations"]]
    assert "untrusted data" in adapter.calls[0]["system_instruction"]


def test_estimate_tool_cannot_invent_missing_api_inputs(client, monkeypatch):
    adapter = install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("estimate_cost", {}, "estimate-1"),)),
        ModelReply(text="Your cost is $10."),
    )
    response = client.post(
        "/api/chat",
        json={"session_id": "session-a", "message": "Estimate an MRI."},
    )

    assert response.status_code == 200
    assert "provide explicit estimate_input" in response.json()["answer"]
    assert response.json()["estimate"] is None
    assert len(adapter.calls) == 1


def test_unconfirmed_plan_rejects_estimate_before_provider_call(client, monkeypatch):
    associate_context(client, confirmed=False)
    monkeypatch.setattr(
        main,
        "chat_adapter_factory",
        lambda: pytest.fail("provider must not be called for an unconfirmed plan"),
    )

    response = client.post(
        "/api/chat",
        json={
            "session_id": "session-a",
            "message": "Estimate an MRI.",
            "estimate_input": {"service": "MRI", "allowed_amount": 3000},
        },
    )

    assert response.status_code == 400
    assert "confirmed" in response.json()["detail"].lower()


def test_missing_required_plan_term_rejects_estimate(client, monkeypatch):
    associate_context(client, include_oop=False)
    monkeypatch.setattr(
        main,
        "chat_adapter_factory",
        lambda: pytest.fail("provider must not be called when required terms are missing"),
    )

    response = client.post(
        "/api/chat",
        json={
            "session_id": "session-a",
            "message": "Estimate an MRI.",
            "estimate_input": {"service": "MRI", "allowed_amount": 3000},
        },
    )

    assert response.status_code == 400
    assert "out_of_pocket_max" in response.json()["detail"]


def test_session_documents_and_citations_are_isolated(client, monkeypatch):
    associate_context(
        client,
        "session-a",
        session_doc_id="doc-a",
        text="The in-network individual deductible is $1,000.",
    )
    associate_context(
        client,
        "session-b",
        session_doc_id="doc-b",
        deductible=9000,
        text="The in-network individual deductible is $9,000.",
    )
    adapter = install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("search_plan_documents", {}, "search-a"),)),
        ModelReply(text="Your deductible is $1,000."),
        ModelReply(tool_calls=(ToolCall("search_plan_documents", {}, "search-b"),)),
        ModelReply(text="Your deductible is $9,000."),
    )

    first = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "What is my deductible?"}
    )
    second = client.post(
        "/api/chat", json={"session_id": "session-b", "message": "What is my deductible?"}
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["citations"] == [{"doc_id": "doc-a", "page": 1}]
    assert second.json()["citations"] == [{"doc_id": "doc-b", "page": 1}]
    first_tool_results = adapter.calls[1]["messages"][-1].tool_results
    second_tool_results = adapter.calls[3]["messages"][-1].tool_results
    assert "$1,000" in str(first_tool_results[0].response)
    assert "$9,000" not in str(first_tool_results[0].response)
    assert "$9,000" in str(second_tool_results[0].response)
    assert "$1,000" not in str(second_tool_results[0].response)


def test_missing_document_evidence_uses_fixed_reply(client, monkeypatch):
    associate_context(client, text="The plan has a $1,000 deductible.")
    adapter = install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("search_plan_documents", {}, "search-1"),)),
    )

    response = client.post(
        "/api/chat",
        json={"session_id": "session-a", "message": "What is the ER copay?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == NOT_FOUND_REPLY
    assert response.json()["citations"] == []
    assert len(adapter.calls) == 1


def test_refusal_tool_uses_existing_fixed_reply(client, monkeypatch):
    install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("refuse_out_of_scope", {}, "refuse-1"),)),
    )
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "Write my travel itinerary."}
    )

    assert response.status_code == 200
    assert response.json()["answer"] == REFUSAL_REPLY
    assert response.json()["refused"] is True


def test_audit_requests_report_unavailable_without_mock_findings(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "chat_adapter_factory",
        lambda: pytest.fail("audit availability is deterministic and needs no Gemini call"),
    )
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "Audit this bill for duplicates."}
    )

    assert response.status_code == 200
    assert "unavailable" in response.json()["answer"].lower()
    assert "mock" in response.json()["answer"].lower()
    assert response.json()["audit"] is None


def test_invalid_tool_arguments_are_rejected(client, monkeypatch):
    install_adapter(
        monkeypatch,
        ModelReply(
            tool_calls=(
                ToolCall("search_plan_documents", {"query": "invented query"}, "bad-args"),
            )
        ),
    )
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "What is my deductible?"}
    )

    assert response.status_code == 502
    assert "invalid tool arguments" in response.json()["detail"].lower()


def test_unknown_tool_is_rejected(client, monkeypatch):
    install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("delete_session", {}, "unknown"),)),
    )
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "What is my deductible?"}
    )

    assert response.status_code == 502
    assert "unsupported tool" in response.json()["detail"].lower()


def test_tool_call_limit_is_enforced(client, monkeypatch):
    monkeypatch.setenv("MAX_TOOL_CALLS_PER_TURN", "1")
    adapter = install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("search_plan_documents", {}, "search-1"),)),
        ModelReply(tool_calls=(ToolCall("refuse_out_of_scope", {}, "refuse-2"),)),
    )
    associate_context(client)
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "What is my deductible?"}
    )

    assert response.status_code == 502
    assert "tool-call limit" in response.json()["detail"]
    assert len(adapter.calls) == 2


def test_turn_limit_is_enforced(client, monkeypatch):
    monkeypatch.setenv("MAX_TURNS_PER_SESSION", "1")
    adapter = install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("refuse_out_of_scope", {}, "first"),)),
    )
    first = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "Write a poem."}
    )
    second = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "Write another poem."}
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert "turn limit" in second.json()["detail"].lower()
    assert len(adapter.calls) == 1


def test_output_token_limit_is_passed_to_adapter(client, monkeypatch):
    monkeypatch.setenv("MAX_OUTPUT_TOKENS", "37")
    adapter = install_adapter(
        monkeypatch,
        ModelReply(tool_calls=(ToolCall("search_plan_documents", {}, "search"),)),
        ModelReply(text="Your deductible is in the document."),
    )
    associate_context(client)
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "What is my deductible?"}
    )

    assert response.status_code == 200
    assert all(call["max_output_tokens"] == 37 for call in adapter.calls)


def test_provider_error_is_safe(client, monkeypatch):
    class BrokenAdapter:
        def generate(self, *args, **kwargs):
            raise GeminiProviderError("provider failed with private details")

    monkeypatch.setattr(main, "chat_adapter_factory", lambda: BrokenAdapter())
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "What is my deductible?"}
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Gemini provider request failed."
    assert "private details" not in response.text
    assert "GEMINI_API_KEY" not in response.text


def test_missing_gemini_key_returns_clear_service_error(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(main, "chat_adapter_factory", main.create_gemini_adapter)
    response = client.post(
        "/api/chat", json={"session_id": "session-a", "message": "What is my deductible?"}
    )

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_session_store_is_bounded_and_expires():
    now = [100.0]
    store = ChatSessionStore(max_sessions=1, ttl_seconds=60, clock=lambda: now[0])
    first = store.begin_turn("first", max_turns=10)
    assert first.turns == 1
    with pytest.raises(ChatSessionLimitError):
        store.begin_turn("second", max_turns=10)

    now[0] += 61
    second = store.begin_turn("second", max_turns=10)
    assert second.turns == 1
    with pytest.raises(ChatSessionLimitError):
        store.begin_turn("third", max_turns=10)


def test_turn_store_rejects_turns_after_configured_cap():
    store = ChatSessionStore()
    store.begin_turn("session", max_turns=1)
    with pytest.raises(ChatTurnLimitError):
        store.begin_turn("session", max_turns=1)
