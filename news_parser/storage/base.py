from abc import ABC, abstractmethod
from typing import Any

from news_parser.models import NewsItem

# Идентификатор записи в конкретном хранилище (в Postgres — bigint).
RecordId = Any


class Storage(ABC):
    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def existing_ids(self, source_id: str, external_ids: list[str]) -> set[str]:
        """Какие из external_ids источника уже сохранены."""

    @abstractmethod
    def insert(self, item: NewsItem, status: str, error: str | None) -> bool:
        """Сохранить новость. Возвращает False, если она уже есть."""

    @abstractmethod
    def pending(self, source_id: str, limit: int = 100) -> list[tuple[RecordId, int, NewsItem]]:
        """Новости, текст которых нужно попробовать получить снова: (id, попыток, новость)."""

    @abstractmethod
    def update_content(
        self,
        record_id: RecordId,
        content_html: str | None,
        content_text: str | None,
        status: str,
        error: str | None,
    ) -> None:
        """Записать результат очередной попытки получить текст (счётчик попыток +1)."""

    @abstractmethod
    def get_state(self, source_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def save_state(self, source_id: str, state: dict[str, Any], stats: dict[str, Any]) -> None: ...
