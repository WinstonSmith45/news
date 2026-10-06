from alembic import command
from alembic.config import Config


def run_migrations(database_url: str) -> None:
    """Довести схему БД до последней миграции (news_parser/migrations)."""
    # Конфиг собирается в коде: сервису не нужен alembic.ini и не важна рабочая папка.
    config = Config()
    config.set_main_option("script_location", "news_parser:migrations")
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")
