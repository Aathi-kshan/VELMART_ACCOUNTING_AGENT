"""P8 Lite Slice 7 — a `propose_update` tool call made during a real
`/ai/sessions/{id}/messages` conversation surfaces as a fully-shaped
`proposal` in the HTTP response. `call_model`/`classify_intent` are mocked
at the orchestrator's own imported names, the same convention P7's
`test_orchestrator_gating.py` established — this proves the response
wiring, not real model behaviour (that's Slice 14's job).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.ai import orchestrator as orchestrator_module
from app.ai.providers.openrouter import ModelResponse, ToolCall


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def ai_session_id(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> uuid.UUID:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post("/ai/sessions", headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


@pytest.fixture
async def staff_record(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> dict:
    headers = await _owner_headers(client, owner_password)
    page_resp = await client.post(
        "/pages",
        json={
            "name": "Staff",
            "columns": [
                {"name": "Employee", "data_type": "TEXT"},
                {"name": "Salary", "data_type": "CURRENCY"},
            ],
        },
        headers=headers,
    )
    assert page_resp.status_code == 201, page_resp.text
    page = page_resp.json()
    record_resp = await client.post(
        f"/pages/{page['id']}/records",
        json={
            "occurred_at": "2026-01-05T09:00:00Z",
            "data": {"employee": "John Perera", "salary": "60000.00"},
        },
        headers=headers,
    )
    assert record_resp.status_code == 201, record_resp.text
    return record_resp.json()


def _mock_propose_then_answer(monkeypatch: pytest.MonkeyPatch, record_id: str) -> None:
    call_count = {"n": 0}

    async def fake_classify_intent(*args: object, **kwargs: object) -> str:
        return "question"

    async def fake_call_model(*args: object, **kwargs: object) -> ModelResponse:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ModelResponse(
                content=None,
                prompt_tokens=20,
                completion_tokens=10,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="propose_update",
                        arguments={
                            "page_key": "staff",
                            "record_id": record_id,
                            "changes": {"salary": "75000.00"},
                        },
                    )
                ],
            )
        return ModelResponse(
            content="I've prepared an update to John's salary. Please review.",
            prompt_tokens=15,
            completion_tokens=8,
            tool_calls=[],
        )

    monkeypatch.setattr(orchestrator_module, "classify_intent", fake_classify_intent)
    monkeypatch.setattr(orchestrator_module, "call_model", fake_call_model)


class TestProposalSurfacesInTheHttpResponse:
    async def test_response_carries_a_fully_shaped_proposal(
        self,
        client: AsyncClient,
        owner_password: str,
        ai_session_id: uuid.UUID,
        staff_record: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_propose_then_answer(monkeypatch, staff_record["id"])
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "Change John Perera's salary to 75000."},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["proposal"] is not None
        proposal = body["proposal"]
        assert proposal["page"] == "Staff"
        assert proposal["summary"]
        assert proposal["expires_at"]

        changes = {c["column"]: (c["before"], c["after"]) for c in proposal["changes"]}
        assert changes["salary"] == ("60000.00", "75000.00")

        # The record itself is untouched — only a proposal was created.
        record_resp = await client.get(f"/records/{staff_record['id']}", headers=headers)
        assert record_resp.status_code == 200, record_resp.text
        assert record_resp.json()["data"]["salary"] == "60000.00"

    async def test_a_pure_read_message_has_no_proposal(
        self,
        client: AsyncClient,
        owner_password: str,
        ai_session_id: uuid.UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_classify_intent(*args: object, **kwargs: object) -> str:
            return "question"

        async def fake_call_model(*args: object, **kwargs: object) -> ModelResponse:
            return ModelResponse(
                content="Nothing to report.", prompt_tokens=5, completion_tokens=3, tool_calls=[]
            )

        monkeypatch.setattr(orchestrator_module, "classify_intent", fake_classify_intent)
        monkeypatch.setattr(orchestrator_module, "call_model", fake_call_model)
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(
            f"/ai/sessions/{ai_session_id}/messages",
            json={"message": "How much did we spend last month?"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["proposal"] is None
