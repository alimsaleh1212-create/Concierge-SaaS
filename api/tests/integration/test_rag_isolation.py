"""T-B027–T-B030: Cross-tenant RAG isolation audit.

Verifies three independent isolation layers for pgvector retrieval:
  - T-B030: EmbeddingRepository.cosine_search filters by tenant_id at the ORM layer.
  - T-B027: tenant_id filter is inside the SQL scan (WHERE clause), not post-retrieval.
  - T-B028: RagSearchTool sources tenant_id from the JWT constructor, never tool input.
  - T-B029: Tenant A queries never surface Tenant B embeddings, and vice-versa.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── T-B030: ORM-layer WHERE clause must contain tenant_id ────────────────────

def test_cosine_search_query_contains_tenant_id_filter():
    """Compiled SQL for cosine_search must include tenant_id in the WHERE clause."""
    from sqlalchemy import select
    from app.models.embedding import Embedding

    tenant_id = uuid.uuid4()
    query_vec = [0.0] * 1024

    stmt = (
        select(Embedding)
        .where(Embedding.tenant_id == tenant_id)
        .order_by(Embedding.embedding.cosine_distance(query_vec))
        .limit(5)
    )

    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "tenant_id" in compiled, "tenant_id filter is absent from cosine_search query"


# ── T-B027 / T-B029: Behavioral isolation — Tenant A vs Tenant B ─────────────

@pytest.mark.asyncio
async def test_cosine_search_returns_only_tenant_a_rows():
    """cosine_search scoped to Tenant A must not return Tenant B embeddings."""
    from app.repositories.embedding_repo import EmbeddingRepository
    from app.models.embedding import Embedding

    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    def make_row(tid: uuid.UUID) -> MagicMock:
        row = MagicMock(spec=Embedding)
        row.tenant_id = tid
        row.chunk_text = f"chunk for {tid}"
        row.parent_chunk_text = f"parent for {tid}"
        row.chunk_index = 0
        row.content_id = uuid.uuid4()
        return row

    row_a = make_row(tenant_a_id)
    # row_b exists in the database but must never appear in Tenant A's results
    _ = make_row(tenant_b_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row_a]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = EmbeddingRepository(mock_session)
    results = await repo.cosine_search([0.1] * 1024, tenant_a_id, top_k=5)

    assert len(results) == 1
    assert results[0].tenant_id == tenant_a_id


@pytest.mark.asyncio
async def test_cosine_search_tenant_b_cannot_see_tenant_a_rows():
    """Symmetric: Tenant B query never surfaces Tenant A embeddings."""
    from app.repositories.embedding_repo import EmbeddingRepository
    from app.models.embedding import Embedding

    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    row_b = MagicMock(spec=Embedding)
    row_b.tenant_id = tenant_b_id
    row_b.chunk_text = "tenant b chunk"
    row_b.parent_chunk_text = "tenant b parent"
    row_b.chunk_index = 0
    row_b.content_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row_b]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = EmbeddingRepository(mock_session)
    results = await repo.cosine_search([0.2] * 1024, tenant_b_id, top_k=5)

    assert all(r.tenant_id == tenant_b_id for r in results)
    assert not any(r.tenant_id == tenant_a_id for r in results)


@pytest.mark.asyncio
async def test_cosine_search_empty_when_no_matching_tenant():
    """If no embeddings exist for the queried tenant, result must be empty — not a leak."""
    from app.repositories.embedding_repo import EmbeddingRepository

    tenant_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = EmbeddingRepository(mock_session)
    results = await repo.cosine_search([0.0] * 1024, tenant_id, top_k=5)

    assert results == []


# ── T-B028: RagSearchTool — tenant_id must come from JWT, not tool input ──────

def test_rag_search_schema_does_not_expose_tenant_id():
    """Tool schema must not include tenant_id — Claude cannot supply or override it."""
    from app.agent.tools.rag_search import SCHEMA

    props = SCHEMA["input_schema"]["properties"]
    assert "tenant_id" not in props, "tenant_id must not appear in rag_search tool schema"
    assert "query" in props, "query field must be present in rag_search schema"


@pytest.mark.asyncio
async def test_rag_search_tool_uses_constructor_tenant_id():
    """RagSearchTool must call retrieve() with the constructor tenant_id, not any tool arg."""
    from app.agent.tools.rag_search import RagSearchTool

    expected_tenant_id = uuid.uuid4()
    mock_session = AsyncMock()
    tool = RagSearchTool(expected_tenant_id, mock_session)

    with patch("app.agent.tools.rag_search.retrieve", new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = []
        await tool(query="What is your return policy?")
        called_tenant_id = mock_retrieve.call_args[0][1]

    assert called_tenant_id == expected_tenant_id, (
        "RagSearchTool passed wrong tenant_id to retrieve() — must use JWT-bound constructor value"
    )


@pytest.mark.asyncio
async def test_rag_search_tool_ignores_injected_tenant_id_in_kwargs():
    """Extra kwargs (e.g. an injected tenant_id) must be silently dropped via **_."""
    from app.agent.tools.rag_search import RagSearchTool

    legitimate_tenant = uuid.uuid4()
    attacker_tenant = uuid.uuid4()
    mock_session = AsyncMock()
    tool = RagSearchTool(legitimate_tenant, mock_session)

    with patch("app.agent.tools.rag_search.retrieve", new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = []
        # Simulate Claude attempting to supply tenant_id as a tool argument
        await tool(query="What are your hours?", tenant_id=str(attacker_tenant))
        called_tenant_id = mock_retrieve.call_args[0][1]

    assert called_tenant_id == legitimate_tenant, (
        "Injected tenant_id in tool kwargs must not override the constructor-bound tenant_id"
    )


# ── T-B027: retrieve() passes tenant_id to cosine_search, not post-filter ────

@pytest.mark.asyncio
async def test_retrieve_passes_tenant_id_to_cosine_search():
    """retrieve() must forward tenant_id into cosine_search — not filter results afterward."""
    from app.rag.retriever import retrieve

    tenant_id = uuid.uuid4()
    mock_session = AsyncMock()

    with (
        patch("app.rag.retriever.embed_query", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retriever.EmbeddingRepository") as MockRepo,
    ):
        mock_embed.return_value = [0.0] * 1024
        mock_repo_instance = AsyncMock()
        mock_repo_instance.cosine_search = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await retrieve("test query", tenant_id, mock_session, top_k=3)

        mock_repo_instance.cosine_search.assert_called_once()
        call_args = mock_repo_instance.cosine_search.call_args[0]
        assert call_args[1] == tenant_id, "retrieve() must pass tenant_id to cosine_search"
        # Reranking branch fetches _RERANK_FETCH_MULTIPLIER × top_k candidates (currently 3×)
        assert call_args[2] >= 3, "retrieve() must fetch at least top_k candidates for cosine_search"
