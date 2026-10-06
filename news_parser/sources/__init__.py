# Импорт модулей регистрирует типы источников в SOURCE_TYPES.
from news_parser.sources import rss  # noqa: F401
from news_parser.sources.base import SOURCE_TYPES, FetchResult, Source, create_source

__all__ = ["SOURCE_TYPES", "FetchResult", "Source", "create_source"]
