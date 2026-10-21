import asyncio
import logging

import voyageai

from app.core.config import get_settings

logger = logging.getLogger(__name__)

VOYAGE_MODEL = "voyage-4"
RERANK_MODEL = "rerank-3"
EMBEDDING_DIM = 1024
_MAX_ATTEMPTS = 3
# Voyage accounts without a payment method are capped at 3 requests/min, so a
# rate-limited call waits out the window instead of failing (slow, but succeeds).
_RATE_LIMIT_ATTEMPTS = 6
_RATE_LIMIT_WAIT_S = 21

_client: voyageai.AsyncClient | None = None
_sync_client: voyageai.Client | None = None


def get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        _client = voyageai.AsyncClient(api_key=get_settings().VOYAGE_API_KEY)
    return _client


def _get_sync_client() -> voyageai.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = voyageai.Client(api_key=get_settings().VOYAGE_API_KEY)
    return _sync_client


async def embed(texts: list[str], *, input_type: str = "document") -> list[list[float]]:
    """Embed a batch of texts with retry.

    Rate-limit errors wait out the per-minute window (up to 6 tries); other errors
    get 3 attempts with exponential backoff.
    """
    attempt = 0
    rate_limited = 0
    while True:
        try:
            result = await get_client().embed(texts, model=VOYAGE_MODEL, input_type=input_type)
            return result.embeddings
        except voyageai.error.RateLimitError:
            rate_limited += 1
            if rate_limited >= _RATE_LIMIT_ATTEMPTS:
                raise
            logger.warning(
                "voyage rate limited (try %d/%d), waiting %ds",
                rate_limited,
                _RATE_LIMIT_ATTEMPTS,
                _RATE_LIMIT_WAIT_S,
            )
            await asyncio.sleep(_RATE_LIMIT_WAIT_S)
        except Exception:
            attempt += 1
            if attempt >= _MAX_ATTEMPTS:
                raise
            await asyncio.sleep(2 ** (attempt - 1))


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    results = await embed([text], input_type="query")
    return results[0]


async def rerank(query: str, documents: list[str], top_k: int = 5) -> list[int]:
    """Rerank documents by relevance to query using voyage rerank-3.

    Returns indices into `documents` in ranked order (most relevant first).
    Runs the synchronous Voyage SDK call in a thread pool to avoid blocking.
    """
    def _call() -> list[int]:
        result = _get_sync_client().rerank(
            query, documents, model=RERANK_MODEL, top_k=top_k
        )
        return [r.index for r in result.results]

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return await asyncio.to_thread(_call)
        except Exception as exc:
            last_exc = exc
            logger.warning("rerank attempt %d failed: %s", attempt + 1, exc)
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(2**attempt)

    raise last_exc  # type: ignore[misc]
