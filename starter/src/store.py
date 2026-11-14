"""Store and search vectors with metadata filtering using PostgreSQL 16 + pgvector."""
import json
from typing import Any
import psycopg
from .models import Chunk


class PgVectorStore:
    """Persistent PostgreSQL + pgvector store supporting idempotent upsert and exact cosine search."""

    PERMITTED_FILTER_KEYS = {
        "section",
        "document_id",
        "source",
        "page",
        "document_type",
        "language",
    }

    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url or not database_url.strip():
            raise ValueError("database_url must not be empty")
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")
        self.database_url = database_url.strip()
        self.dimensions = int(dimensions)

    def create_schema(self) -> None:
        """Create pgvector extension, table with vector column, and metadata indexes."""
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                # Check if table exists with a different vector dimension
                dim_literal = int(self.dimensions)
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                        strategy TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        section TEXT NOT NULL DEFAULT '',
                        text TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding vector({dim_literal}) NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (strategy, chunk_id)
                    );
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_chunks_strategy_section ON rag_chunks (strategy, section);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_chunks_strategy_doc_page ON rag_chunks (strategy, document_id, page);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_chunks_metadata_gin ON rag_chunks USING GIN (metadata);"
                )
            conn.commit()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Validate lengths/dimensions, prune obsolete chunks on document update, and upsert idempotently."""
        if not strategy or not strategy.strip():
            raise ValueError("strategy must not be empty")
        if len(chunks) != len(vectors):
            raise ValueError(f"chunks count ({len(chunks)}) != vectors count ({len(vectors)})")
        if not chunks:
            return

        seen_ids: set[str] = set()
        doc_to_chunk_ids: dict[str, list[str]] = {}

        for c, v in zip(chunks, vectors):
            if len(v) != self.dimensions:
                raise ValueError(
                    f"Vector dimension mismatch for chunk {c.chunk_id}: {len(v)} != {self.dimensions}"
                )
            if c.chunk_id in seen_ids:
                raise ValueError(f"Duplicate chunk_id in batch: {c.chunk_id}")
            seen_ids.add(c.chunk_id)
            doc_to_chunk_ids.setdefault(c.document_id, []).append(c.chunk_id)

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                # Remove obsolete chunks for each source document being re-ingested under this strategy
                for doc_id, active_ids in doc_to_chunk_ids.items():
                    cur.execute(
                        """
                        DELETE FROM rag_chunks
                        WHERE strategy = %s
                          AND document_id = %s
                          AND NOT (chunk_id = ANY(%s));
                        """,
                        (strategy, doc_id, active_ids),
                    )

                # Upsert all current chunks without duplicating rows
                upsert_sql = """
                    INSERT INTO rag_chunks (
                        strategy, chunk_id, document_id, source, page, section, text, metadata, embedding, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, NOW())
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source = EXCLUDED.source,
                        page = EXCLUDED.page,
                        section = EXCLUDED.section,
                        text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW();
                """
                for c, v in zip(chunks, vectors):
                    section = str(c.metadata.get("section", ""))
                    meta_With_core = dict(c.metadata)
                    meta_With_core.update(
                        {
                            "document_id": c.document_id,
                            "source": c.source,
                            "page": c.page,
                            "section": section,
                        }
                    )
                    vec_str = "[" + ",".join(f"{float(x):.8f}" for x in v) + "]"
                    cur.execute(
                        upsert_sql,
                        (
                            strategy,
                            c.chunk_id,
                            c.document_id,
                            c.source,
                            int(c.page),
                            section,
                            c.text,
                            json.dumps(meta_With_core, ensure_ascii=False),
                            vec_str,
                        ),
                    )
            conn.commit()

    def count_chunks(self, strategy: str) -> int:
        """Return the number of stored chunks for a given strategy."""
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM rag_chunks WHERE strategy = %s;",
                    (strategy,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata in SQL, rank by exact cosine distance (<=>), and return top-k."""
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"Query vector dimension mismatch: {len(query_vector)} != {self.dimensions}"
            )
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        vec_str = "[" + ",".join(f"{float(x):.8f}" for x in query_vector) + "]"
        where_clauses = ["strategy = %s"]
        params: list[Any] = [vec_str, strategy]

        if filters:
            for key, val in filters.items():
                if val is None:
                    continue
                if key not in self.PERMITTED_FILTER_KEYS:
                    raise ValueError(f"Unsupported filter key: {key}")
                if key == "section":
                    where_clauses.append("section = %s")
                    params.append(str(val))
                elif key == "document_id":
                    where_clauses.append("document_id = %s")
                    params.append(str(val))
                elif key == "source":
                    where_clauses.append("source = %s")
                    params.append(str(val))
                elif key == "page":
                    where_clauses.append("page = %s")
                    params.append(int(val))
                else:
                    where_clauses.append("metadata ->> %s = %s")
                    params.extend([key, str(val)])

        params.extend([vec_str, int(top_k)])
        where_sql = " AND ".join(where_clauses)

        query_sql = f"""
            SELECT
                chunk_id,
                document_id,
                source,
                page,
                section,
                text,
                1.0 - (embedding <=> %s::vector) AS cosine_score,
                metadata
            FROM rag_chunks
            WHERE {where_sql}
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s;
        """

        results: list[dict[str, Any]] = []
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query_sql, params)
                rows = cur.fetchall()
                for rank, row in enumerate(rows, start=1):
                    chunk_id, doc_id, source, page, section, text, score, metadata = row
                    meta_dict = metadata if isinstance(metadata, dict) else json.loads(metadata)
                    results.append(
                        {
                            "rank": rank,
                            "chunk_id": chunk_id,
                            "document_id": doc_id,
                            "source": source,
                            "page": int(page),
                            "section": section,
                            "text": text,
                            "score": round(float(score), 6),
                            "metadata": meta_dict,
                        }
                    )
        return results
