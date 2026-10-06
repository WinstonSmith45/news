# Импорт модулей регистрирует стратегии в EXTRACTORS.
from news_parser.extractors import css, from_source  # noqa: F401
from news_parser.extractors.base import EXTRACTORS, ContentExtractor, ContentNotFound, create_extractor

__all__ = ["EXTRACTORS", "ContentExtractor", "ContentNotFound", "create_extractor"]
