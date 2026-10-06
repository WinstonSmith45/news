"""news: created_at, CHECK on content_status

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Когда новость попала в базу. У старых записей — updated_at: он ставится при вставке
    # и меняется только при повторных попытках получить текст, так что точнее времени миграции.
    op.execute("ALTER TABLE news ADD COLUMN created_at timestamptz")
    op.execute("UPDATE news SET created_at = updated_at")
    op.execute("ALTER TABLE news ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE news ALTER COLUMN created_at SET NOT NULL")

    # Значения ContentStatus (news_parser/models.py).
    op.execute("""
        ALTER TABLE news ADD CONSTRAINT news_content_status_check
            CHECK (content_status IN ('ok', 'pending', 'failed'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE news DROP CONSTRAINT news_content_status_check")
    op.execute("ALTER TABLE news DROP COLUMN created_at")
