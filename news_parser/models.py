from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NewsItem:
    """Новость в едином для всех типов источников виде."""

    source_id: str
    source_type: str
    # Уникальный идентификатор внутри источника (для RSS — нормализованная ссылка).
    external_id: str
    url: str | None = None
    title: str | None = None
    content_html: str | None = None
    # Текст без разметки, получается из content_html.
    content_text: str | None = None
    categories: list[str] = field(default_factory=list)
    published_at: datetime | None = None


class ContentStatus:
    # Допустимые значения закреплены в БД (CHECK news_content_status_check): новый статус — через миграцию.
    OK = "ok"
    PENDING = "pending"
    FAILED = "failed"
