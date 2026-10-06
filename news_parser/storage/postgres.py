from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from news_parser.models import ContentStatus, NewsItem
from news_parser.storage.base import Storage

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS news (
    id               bigserial PRIMARY KEY,
    source_id        text NOT NULL,
    source_type      text NOT NULL,
    external_id      text NOT NULL,
    url              text,
    title            text,
    content_html     text,
    content_text     text,
    categories       text[] NOT NULL DEFAULT '{}',
    published_at     timestamptz,
    content_status   text NOT NULL,
    content_attempts int  NOT NULL DEFAULT 1,
    content_error    text,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    -- Полнотекстовый поиск: заголовок важнее текста.
    search_vector    tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(content_text, '')), 'C')
    ) STORED,
    UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS news_source_published_idx ON news (source_id, published_at DESC);
CREATE INDEX IF NOT EXISTS news_published_idx ON news (published_at DESC);
CREATE INDEX IF NOT EXISTS news_pending_idx ON news (source_id, id)
    WHERE content_status = 'pending';
CREATE INDEX IF NOT EXISTS news_search_idx ON news USING gin (search_vector);
CREATE INDEX IF NOT EXISTS news_categories_idx ON news USING gin (categories);

CREATE TABLE IF NOT EXISTS source_state (
    source_id   text PRIMARY KEY,
    state       jsonb NOT NULL DEFAULT '{}',
    last_run    jsonb,
    last_run_at timestamptz
);
"""

ITEM_COLUMNS = [
    "source_id", "source_type", "external_id", "url", "title", "content_html",
    "content_text", "categories", "published_at",
]


class PostgresStorage(Storage):
    def __init__(self, dsn: str):
        # Пул сам переподключается, если Postgres перезапустился.
        self._pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=2,
            kwargs={"autocommit": True, "row_factory": dict_row},
            check=ConnectionPool.check_connection,
            open=True,
        )

    def ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(SCHEMA)

    def close(self) -> None:
        self._pool.close()

    # --- новости ---

    def existing_ids(self, source_id: str, external_ids: list[str]) -> set[str]:
        if not external_ids:
            return set()
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT external_id FROM news WHERE source_id = %s AND external_id = ANY(%s)",
                (source_id, external_ids),
            ).fetchall()
        return {row["external_id"] for row in rows}

    def insert(self, item: NewsItem, status: str, error: str | None) -> bool:
        values = [getattr(item, col) for col in ITEM_COLUMNS]
        columns = ", ".join(ITEM_COLUMNS + ["content_status", "content_error"])
        placeholders = ", ".join(["%s"] * (len(ITEM_COLUMNS) + 2))
        with self._pool.connection() as conn:
            row = conn.execute(
                f"INSERT INTO news ({columns}) VALUES ({placeholders}) "
                "ON CONFLICT (source_id, external_id) DO NOTHING RETURNING id",
                [*values, status, error],
            ).fetchone()
        return row is not None

    def pending(self, source_id: str, limit: int = 100) -> list[tuple[int, int, NewsItem]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT id, content_attempts, {', '.join(ITEM_COLUMNS)} FROM news "
                "WHERE source_id = %s AND content_status = %s ORDER BY id LIMIT %s",
                (source_id, ContentStatus.PENDING, limit),
            ).fetchall()
        return [
            (row["id"], row["content_attempts"], NewsItem(**{c: row[c] for c in ITEM_COLUMNS}))
            for row in rows
        ]

    def update_content(
        self,
        record_id: int,
        content_html: str | None,
        content_text: str | None,
        status: str,
        error: str | None,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE news SET content_html = coalesce(%s, content_html), "
                "content_text = coalesce(%s, content_text), content_status = %s, "
                "content_error = %s, content_attempts = content_attempts + 1, updated_at = now() "
                "WHERE id = %s",
                (content_html, content_text, status, error, record_id),
            )

    # --- состояние источников ---

    def get_state(self, source_id: str) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT state FROM source_state WHERE source_id = %s", (source_id,)
            ).fetchone()
        return row["state"] if row else {}

    def save_state(self, source_id: str, state: dict[str, Any], stats: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO source_state (source_id, state, last_run, last_run_at) "
                "VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (source_id) DO UPDATE SET state = EXCLUDED.state, "
                "last_run = EXCLUDED.last_run, last_run_at = EXCLUDED.last_run_at",
                (source_id, Jsonb(state), Jsonb(stats)),
            )
