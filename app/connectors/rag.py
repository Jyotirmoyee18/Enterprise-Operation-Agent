from pgvector import Vector

from app.core.db import connection
from app.connectors.embeddings import embed


def chunks(text: str, size: int = 900, overlap: int = 120):
    text = " ".join(text.split())

    if not text:
        return []

    out = []
    start = 0

    while start < len(text):
        end = min(len(text), start + size)
        out.append(text[start:end])

        if end == len(text):
            break

        start = max(start + 1, end - overlap)

    return out


def ingest(title: str, source: str, text: str):
    pieces = chunks(text)

    if not pieces:
        raise ValueError("Document text is empty")

    with connection() as c:
        for piece in pieces:
            vector = Vector(embed(piece))

            c.execute(
                """
                INSERT INTO knowledge_chunks
                    (title, source, content, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (title, source, piece, vector),
            )

    return {"chunks_indexed": len(pieces)}


def search(query: str, top_k: int = 5):
    vector = Vector(embed(query))

    with connection() as c:
        rows = c.execute(
            """
            SELECT
                title,
                source,
                content,
                1 - (embedding <=> %s::vector) AS score
            FROM knowledge_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, vector, top_k),
        ).fetchall()

    return [dict(row) for row in rows]