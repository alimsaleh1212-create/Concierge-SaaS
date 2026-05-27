from app.core.embedder import embed as _embed


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed a list of document chunks via the Voyage adapter."""
    return await _embed(chunks, input_type="document")
