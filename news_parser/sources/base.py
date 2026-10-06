from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from news_parser.config import ConfigError, SourceConfig
from news_parser.http_client import HttpClient
from news_parser.models import NewsItem


@dataclass
class FetchResult:
    items: list[NewsItem]
    # Новое состояние источника (курсор, id последнего сообщения и т.п.),
    # сохраняется в хранилище и передаётся в следующий вызов fetch().
    state: dict[str, Any] = field(default_factory=dict)


class Source(ABC):
    type: ClassVar[str]

    def __init__(self, config: SourceConfig, http: HttpClient):
        self.config = config
        self.http = http

    @property
    def id(self) -> str:
        return self.config.id

    def option(self, name: str) -> Any:
        value = self.config.options.get(name)
        if value is None:
            raise ConfigError(f"источник {self.id}: не задан параметр {name!r}")
        return value

    @abstractmethod
    def fetch(self, state: dict[str, Any]) -> FetchResult:
        """Вернуть свежие новости источника. Дубли отсеиваются снаружи."""


SOURCE_TYPES: dict[str, type[Source]] = {}


def register_source(cls: type[Source]) -> type[Source]:
    SOURCE_TYPES[cls.type] = cls
    return cls


def create_source(config: SourceConfig, http: HttpClient) -> Source:
    try:
        cls = SOURCE_TYPES[config.type]
    except KeyError:
        raise ConfigError(
            f"источник {config.id}: неизвестный тип {config.type!r}, "
            f"доступны: {', '.join(sorted(SOURCE_TYPES))}"
        ) from None
    return cls(config, http)
