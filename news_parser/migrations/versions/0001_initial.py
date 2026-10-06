"""initial schema: news, source_state

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# IF NOT EXISTS — чтобы на базе, созданной до Alembic (старым ensure_schema), миграция
# прошла без изменений и только записала версию. В следующих миграциях он не нужен.
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
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
        )
    """)

    op.execute(
        "CREATE INDEX IF NOT EXISTS news_source_published_idx ON news (source_id, published_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS news_published_idx ON news (published_at DESC)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS news_pending_idx ON news (source_id, id)
            WHERE content_status = 'pending'
    """)
    op.execute("CREATE INDEX IF NOT EXISTS news_search_idx ON news USING gin (search_vector)")
    op.execute("CREATE INDEX IF NOT EXISTS news_categories_idx ON news USING gin (categories)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS source_state (
            source_id   text PRIMARY KEY,
            state       jsonb NOT NULL DEFAULT '{}',
            last_run    jsonb,
            last_run_at timestamptz
        )
    """)


# Расширение vector не удаляется: оно может быть нужно не только этим таблицам.
def downgrade() -> None:
    op.execute("DROP TABLE source_state")
    op.execute("DROP TABLE news")
