from abc import ABC, abstractmethod
from typing import Any, ClassVar

from news_parser.config import ConfigError
from news_parser.extractors.cleanup import Cleaner
from news_parser.http_client import HttpClient
from news_parser.models import NewsItem


class ContentNotFound(Exception):
    """Полный текст отсутствует, и повторная попытка не поможет."""


class ContentExtractor(ABC):
    strategy: ClassVar[str]
    # Делает ли экстрактор сетевые запросы (тогда между ними выдерживается пауза).
    uses_network: ClassVar[bool] = False

    def __init__(self, options: dict[str, Any], http: HttpClient):
        self.options = options
        self.http = http
        self.cleaner = Cleaner(options)

    def extract(self, item: NewsItem) -> str:
        """Вернуть HTML полного текста новости, очищенный от мусора."""
        html = self.cleaner.clean(self.fetch(item))
        if not html:
            raise ContentNotFound("после очистки полный текст пуст")
        return html

    @abstractmethod
    def fetch(self, item: NewsItem) -> str:
        """Получить HTML полного текста новости как есть."""


EXTRACTORS: dict[str, type[ContentExtractor]] = {}

DEFAULT_STRATEGY = "from_source"


def register_extractor(cls: type[ContentExtractor]) -> type[ContentExtractor]:
    EXTRACTORS[cls.strategy] = cls
    return cls


def create_extractor(source_id: str, content: dict[str, Any], http: HttpClient) -> ContentExtractor:
    options = dict(content)
    strategy = options.pop("strategy", DEFAULT_STRATEGY)
    try:
        cls = EXTRACTORS[strategy]
    except KeyError:
        raise ConfigError(
            f"источник {source_id}: неизвестная стратегия content {strategy!r}, "
            f"доступны: {', '.join(sorted(EXTRACTORS))}"
        ) from None
    return cls(options, http)
