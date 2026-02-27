"""Hybrid search service - ChromaDB vector search + SQLite FTS."""

from __future__ import annotations

import contextlib

import aiosqlite

try:
    import chromadb
except ImportError:
    chromadb = None  # type: ignore[assignment]

_chroma_client = None
_cards_collection = None
_comments_collection = None


def init_chromadb(persist_dir: str) -> None:
    """Initialize ChromaDB client and collections."""
    global _chroma_client, _cards_collection, _comments_collection

    if chromadb is None:
        return

    _chroma_client = chromadb.PersistentClient(path=persist_dir)
    _cards_collection = _chroma_client.get_or_create_collection(
        name="kira_cards",
        metadata={"hnsw:space": "cosine"},
    )
    _comments_collection = _chroma_client.get_or_create_collection(
        name="kira_comments",
        metadata={"hnsw:space": "cosine"},
    )


def index_card(card: dict) -> None:
    """Index a card in ChromaDB."""
    if _cards_collection is None:
        return

    doc = f"{card['title']}\n{card.get('description', '')}"
    metadata = {
        "board_id": card.get("board_id", ""),
        "column_id": card.get("column_id", ""),
        "priority": card.get("priority", "medium"),
        "assignee_id": card.get("assignee_id") or "",
    }

    _cards_collection.upsert(
        ids=[card["id"]],
        documents=[doc],
        metadatas=[metadata],
    )


def index_comment(comment: dict, board_id: str) -> None:
    """Index a comment in ChromaDB."""
    if _comments_collection is None:
        return

    _comments_collection.upsert(
        ids=[comment["id"]],
        documents=[comment["content"]],
        metadatas=[
            {
                "card_id": comment["card_id"],
                "board_id": board_id,
                "user_id": comment["user_id"],
                "is_agent_output": str(comment.get("is_agent_output", 0)),
            }
        ],
    )


def remove_card(card_id: str) -> None:
    """Remove a card from the search index."""
    if _cards_collection is None:
        return
    with contextlib.suppress(Exception):
        _cards_collection.delete(ids=[card_id])


async def search(
    db: aiosqlite.Connection,
    query: str,
    board_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Hybrid search: vector search in ChromaDB, then enrich from SQLite."""
    if _cards_collection is None:
        # Fallback to SQL LIKE search
        return await _sql_search(db, query, board_id, limit)

    # Vector search
    where_filter = {"board_id": board_id} if board_id else None
    try:
        results = _cards_collection.query(
            query_texts=[query],
            n_results=limit,
            where=where_filter,
        )
    except Exception:
        return await _sql_search(db, query, board_id, limit)

    if not results or not results["ids"] or not results["ids"][0]:
        return await _sql_search(db, query, board_id, limit)

    card_ids = results["ids"][0]
    distances = results["distances"][0] if results.get("distances") else [0.0] * len(card_ids)

    # Fetch full card data from SQLite
    enriched = []
    for card_id, distance in zip(card_ids, distances, strict=False):
        cursor = await db.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = await cursor.fetchone()
        if row:
            card = dict(row)
            card["_score"] = 1.0 - distance  # Convert distance to similarity
            enriched.append(card)

    # Also do SQL search and merge
    sql_results = await _sql_search(db, query, board_id, limit)
    seen_ids = {c["id"] for c in enriched}
    for sr in sql_results:
        if sr["id"] not in seen_ids:
            sr["_score"] = sr.get("_score", 0.5)
            enriched.append(sr)

    # Sort by score descending
    enriched.sort(key=lambda x: x.get("_score", 0), reverse=True)
    return enriched[:limit]


async def _sql_search(
    db: aiosqlite.Connection,
    query: str,
    board_id: str | None,
    limit: int,
) -> list[dict]:
    """Fallback SQL LIKE search."""
    like_pattern = f"%{query}%"
    if board_id:
        cursor = await db.execute(
            """SELECT * FROM cards
               WHERE board_id = ? AND (title LIKE ? OR description LIKE ?)
               ORDER BY updated_at DESC LIMIT ?""",
            (board_id, like_pattern, like_pattern, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT * FROM cards
               WHERE title LIKE ? OR description LIKE ?
               ORDER BY updated_at DESC LIMIT ?""",
            (like_pattern, like_pattern, limit),
        )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["_score"] = 0.5
        results.append(d)
    return results
