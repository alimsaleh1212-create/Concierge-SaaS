import re
from dataclasses import dataclass


@dataclass
class Chunk:
    child_text: str
    parent_text: str
    chunk_index: int


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk(body: str, child_size: int = 2, parent_size: int = 5) -> list[Chunk]:
    """Split body into parent-child chunk pairs.

    child_size: sentences per child chunk
    parent_size: sentences per parent window (centred on child)
    """
    sentences = _split_sentences(body)
    if not sentences:
        return []

    results: list[Chunk] = []
    for i in range(0, len(sentences), child_size):
        child_sentences = sentences[i : i + child_size]
        child_text = " ".join(child_sentences)

        half = (parent_size - child_size) // 2
        parent_start = max(0, i - half)
        parent_end = min(len(sentences), parent_start + parent_size)
        parent_text = " ".join(sentences[parent_start:parent_end])

        results.append(Chunk(child_text=child_text, parent_text=parent_text, chunk_index=len(results)))

    return results
