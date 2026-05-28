import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import guardrails_client
from app.rag.retriever import retrieve

SCHEMA: dict[str, Any] = {
    "name": "rag_search",
    "description": "Search the business knowledge base for information relevant to the visitor's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
        },
        "required": ["query"],
    },
}


class RagSearchTool:
    name = "rag_search"
    schema = SCHEMA

    def __init__(
        self,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        conversation_id: uuid.UUID | None = None,
    ) -> None:
        # tenant_id and conversation_id sourced from verified JWT — never from tool input arguments
        self.tenant_id = tenant_id
        self.session = session
        self.conversation_id = conversation_id

    async def __call__(self, query: str, **_: Any) -> str:
        chunks = await retrieve(query, self.tenant_id, self.session, top_k=5)
        if not chunks:
            return "No relevant information found in the knowledge base."

        raw_chunks = [
            {"chunk_index": c.chunk_index, "text": c.parent_text, "content_id": str(c.content_id)}
            for c in chunks
        ]
        retrieval_result = await guardrails_client.check_retrieval(
            tenant_id=self.tenant_id,
            conversation_id=self.conversation_id or uuid.UUID(int=0),
            query=query,
            chunks=raw_chunks,
        )
        if not retrieval_result.allowed:
            return "No relevant information found in the knowledge base."

        parts = []
        for i, chunk in enumerate(retrieval_result.filtered_chunks, 1):
            parts.append(f"[{i}] {chunk.get('text', '')}")
        return "\n\n".join(parts)
