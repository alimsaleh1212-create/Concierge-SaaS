import uuid
from types import SimpleNamespace

import pytest

from app.agent.agent import TenantContext
from app.agent import router
from app.agent.tools import rag_search
from app.guardrails_client import RetrievalGuardrailsResult
from app.rag import retrieval_guardrails
from app.rag.retriever import ParentChunk


TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CONVERSATION_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
CONTENT_ID_1 = uuid.UUID("33333333-3333-3333-3333-333333333333")
CONTENT_ID_2 = uuid.UUID("44444444-4444-4444-4444-444444444444")
FALLBACK_TEXT = "I'm sorry, I can't use the retrieved context for this request."


def _chunk(
    *,
    content_id: uuid.UUID,
    chunk_index: int,
    parent_text: str,
    child_text: str = "child",
) -> ParentChunk:
    return ParentChunk(
        chunk_index=chunk_index,
        child_text=child_text,
        parent_text=parent_text,
        content_id=content_id,
    )


def _tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id=TENANT_ID,
        widget_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        conversation_id=CONVERSATION_ID,
        tenant_name="Test Tenant",
        persona="Helpful",
        allowed_topics="questions related to our business",
    )


@pytest.mark.asyncio
async def test_chunks_to_guardrails_payload_uses_parent_text():
    chunks = [
        _chunk(
            content_id=CONTENT_ID_1,
            chunk_index=0,
            parent_text="Parent context",
            child_text="Child match",
        )
    ]

    payload = retrieval_guardrails.chunks_to_guardrails_payload(chunks)

    assert payload == [
        {
            "content_id": str(CONTENT_ID_1),
            "chunk_index": 0,
            "text": "Parent context",
        }
    ]


@pytest.mark.asyncio
async def test_apply_retrieval_guardrails_returns_only_filtered_parent_chunks(monkeypatch):
    chunks = [
        _chunk(content_id=CONTENT_ID_1, chunk_index=0, parent_text="Safe chunk"),
        _chunk(content_id=CONTENT_ID_2, chunk_index=1, parent_text="Blocked chunk"),
    ]
    captured = {}

    async def fake_check_retrieval(**kwargs):
        captured.update(kwargs)
        return RetrievalGuardrailsResult(
            allowed=True,
            filtered_chunks=[
                {
                    "content_id": str(CONTENT_ID_1),
                    "chunk_index": 0,
                    "text": "Safe chunk",
                }
            ],
            blocked_chunk_ids=[f"{CONTENT_ID_2}:1"],
        )

    monkeypatch.setattr(retrieval_guardrails.guardrails_client, "check_retrieval", fake_check_retrieval)

    safe_chunks = await retrieval_guardrails.apply_retrieval_guardrails(
        query="hours",
        chunks=chunks,
        tenant_id=TENANT_ID,
        conversation_id=CONVERSATION_ID,
    )

    assert safe_chunks == [chunks[0]]
    assert captured["tenant_id"] == TENANT_ID
    assert captured["conversation_id"] == CONVERSATION_ID
    assert captured["query"] == "hours"
    assert captured["chunks"] == [
        {"content_id": str(CONTENT_ID_1), "chunk_index": 0, "text": "Safe chunk"},
        {"content_id": str(CONTENT_ID_2), "chunk_index": 1, "text": "Blocked chunk"},
    ]


@pytest.mark.asyncio
async def test_apply_retrieval_guardrails_returns_empty_when_blocked(monkeypatch):
    chunks = [_chunk(content_id=CONTENT_ID_1, chunk_index=0, parent_text="Blocked chunk")]

    async def fake_check_retrieval(**kwargs):
        return RetrievalGuardrailsResult(
            allowed=False,
            filtered_chunks=[],
            blocked_chunk_ids=[f"{CONTENT_ID_1}:0"],
            reason="cross_tenant_attempt",
        )

    monkeypatch.setattr(retrieval_guardrails.guardrails_client, "check_retrieval", fake_check_retrieval)

    safe_chunks = await retrieval_guardrails.apply_retrieval_guardrails(
        query="hours",
        chunks=chunks,
        tenant_id=TENANT_ID,
        conversation_id=CONVERSATION_ID,
    )

    assert safe_chunks == []


@pytest.mark.asyncio
async def test_rag_workflow_uses_safe_chunks_only_before_context(monkeypatch):
    chunks = [
        _chunk(content_id=CONTENT_ID_1, chunk_index=0, parent_text="Safe context"),
        _chunk(content_id=CONTENT_ID_2, chunk_index=1, parent_text="Blocked context"),
    ]
    prompts = []

    async def fake_retrieve(query, tenant_id, session, top_k):
        return chunks

    async def fake_apply(**kwargs):
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["conversation_id"] == CONVERSATION_ID
        return [chunks[0]]

    async def fake_chat_completion(**kwargs):
        prompts.append(kwargs["messages"][-1]["content"])
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="answer")],
        )

    monkeypatch.setattr(router, "retrieve", fake_retrieve)
    monkeypatch.setattr(router, "apply_retrieval_guardrails", fake_apply)
    monkeypatch.setattr(router, "_load_rag_answer", lambda: "Context:\n{{context}}\nQuestion: {{question}}")
    monkeypatch.setattr(router, "chat_completion", fake_chat_completion)

    result = await router._rag_workflow("hours", [], _tenant_context(), session=object())

    assert result.response == "answer"
    assert "Safe context" in prompts[0]
    assert "Blocked context" not in prompts[0]


@pytest.mark.asyncio
async def test_rag_workflow_does_not_call_claude_when_all_chunks_blocked(monkeypatch):
    chunks = [_chunk(content_id=CONTENT_ID_1, chunk_index=0, parent_text="Blocked context")]
    called_claude = False

    async def fake_retrieve(query, tenant_id, session, top_k):
        return chunks

    async def fake_apply(**kwargs):
        return []

    async def fake_chat_completion(**kwargs):
        nonlocal called_claude
        called_claude = True
        return SimpleNamespace(content=[])

    monkeypatch.setattr(router, "retrieve", fake_retrieve)
    monkeypatch.setattr(router, "apply_retrieval_guardrails", fake_apply)
    monkeypatch.setattr(router, "chat_completion", fake_chat_completion)

    result = await router._rag_workflow("hours", [], _tenant_context(), session=object())

    assert result.response == FALLBACK_TEXT
    assert result.tool_used == "rag_search"
    assert called_claude is False


@pytest.mark.asyncio
async def test_rag_search_tool_returns_safe_chunks_only_and_uses_trusted_context(monkeypatch):
    chunks = [
        _chunk(content_id=CONTENT_ID_1, chunk_index=0, parent_text="Safe tool context"),
        _chunk(content_id=CONTENT_ID_2, chunk_index=1, parent_text="Blocked tool context"),
    ]
    captured = {}

    async def fake_retrieve(query, tenant_id, session, top_k):
        return chunks

    async def fake_apply(**kwargs):
        captured.update(kwargs)
        return [chunks[0]]

    monkeypatch.setattr(rag_search, "retrieve", fake_retrieve)
    monkeypatch.setattr(rag_search, "apply_retrieval_guardrails", fake_apply)

    tool = rag_search.RagSearchTool(TENANT_ID, session=object(), conversation_id=CONVERSATION_ID)
    output = await tool(
        query="hours",
        tenant_id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
    )

    assert output == "[1] Safe tool context"
    assert "Blocked tool context" not in output
    assert captured["tenant_id"] == TENANT_ID
    assert captured["conversation_id"] == CONVERSATION_ID


@pytest.mark.asyncio
async def test_rag_search_tool_returns_fallback_when_all_chunks_blocked(monkeypatch):
    chunks = [_chunk(content_id=CONTENT_ID_1, chunk_index=0, parent_text="Blocked tool context")]

    async def fake_retrieve(query, tenant_id, session, top_k):
        return chunks

    async def fake_apply(**kwargs):
        return []

    monkeypatch.setattr(rag_search, "retrieve", fake_retrieve)
    monkeypatch.setattr(rag_search, "apply_retrieval_guardrails", fake_apply)

    tool = rag_search.RagSearchTool(TENANT_ID, session=object(), conversation_id=CONVERSATION_ID)
    output = await tool(query="hours")

    assert output == FALLBACK_TEXT
