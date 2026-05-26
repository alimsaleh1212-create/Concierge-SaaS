import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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

    def __init__(self, tenant_id: uuid.UUID, session: AsyncSession) -> None:
        # tenant_id sourced from verified JWT — never from tool input arguments
        self.tenant_id = tenant_id
        self.session = session

    async def __call__(self, query: str, **_: Any) -> str:
        chunks = await retrieve(query, self.tenant_id, self.session, top_k=5)
        if not chunks:
            return "No relevant information found in the knowledge base."

        parts = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(f"[{i}] {chunk.parent_text}")
        return "\n\n".join(parts)
