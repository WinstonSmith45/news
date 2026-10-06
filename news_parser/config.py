import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    database_url: str
    sources_file: Path
    default_interval: int
    http_timeout: float
    http_max_attempts: int
    http_backoff_base: float
    http_backoff_max: float
    request_delay: float
    content_max_cycles: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", "postgresql://news@localhost:5432/news"),
            sources_file=Path(os.environ.get("SOURCES_FILE", "sources.yaml")),
            default_interval=_env_int("POLL_INTERVAL", 3600),
            http_timeout=_env_float("HTTP_TIMEOUT", 30),
            http_max_attempts=_env_int("HTTP_MAX_ATTEMPTS", 5),
            http_backoff_base=_env_float("HTTP_BACKOFF_BASE", 1),
            http_backoff_max=_env_float("HTTP_BACKOFF_MAX", 30),
            request_delay=_env_float("REQUEST_DELAY", 1),
            content_max_cycles=_env_int("CONTENT_MAX_CYCLES", 3),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )


@dataclass(frozen=True)
class SourceConfig:
    id: str
    type: str
    interval: int
    enabled: bool = True
    # Настройки получения полного текста, см. news_parser.extractors.
    content: dict[str, Any] = field(default_factory=dict)
    # Откуда брать рубрики со страницы новости, см. news_parser.categories.
    categories: dict[str, Any] = field(default_factory=dict)
    # Новости, ссылка которых подходит под одно из выражений, не сохраняются.
    skip_urls: tuple[re.Pattern[str], ...] = ()
    # Если задано — сохраняются только новости, у которых есть хотя бы одна из этих рубрик ленты.
    only_categories: frozenset[str] = frozenset()
    # Все остальные ключи — параметры конкретного типа источника (например, url для rss).
    options: dict[str, Any] = field(default_factory=dict)


class ConfigError(Exception):
    pass


def load_sources(path: Path, default_interval: int) -> list[SourceConfig]:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ConfigError(f"{path}: ожидается список источников")

    configs: list[SourceConfig] = []
    seen: set[str] = set()
    for entry in raw:
        entry = dict(entry)
        source_id = entry.pop("id", None)
        source_type = entry.pop("type", None)
        if not source_id or not source_type:
            raise ConfigError(f"{path}: у источника должны быть заданы id и type: {entry}")
        if source_id in seen:
            raise ConfigError(f"{path}: повторяющийся id источника: {source_id}")
        seen.add(source_id)
        configs.append(
            SourceConfig(
                id=source_id,
                type=source_type,
                interval=int(entry.pop("interval", default_interval)),
                enabled=bool(entry.pop("enabled", True)),
                content=entry.pop("content", None) or {},
                categories=entry.pop("categories", None) or {},
                skip_urls=_compile_patterns(source_id, entry.pop("skip_urls", None)),
                only_categories=_categories(source_id, entry.pop("only_categories", None)),
                options=entry,
            )
        )
    return configs


def _categories(source_id: str, raw: Any) -> frozenset[str]:
    values = [raw] if isinstance(raw, str) else list(raw or [])
    if not all(isinstance(v, str) and v.strip() for v in values):
        raise ConfigError(f"источник {source_id}: only_categories — строка или список непустых строк")
    return frozenset(v.strip().casefold() for v in values)


def _compile_patterns(source_id: str, raw: Any) -> tuple[re.Pattern[str], ...]:
    patterns = [raw] if isinstance(raw, str) else list(raw or [])
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except (re.error, TypeError) as e:
            raise ConfigError(f"источник {source_id}: некорректное выражение в skip_urls {pattern!r}: {e}") from None
    return tuple(compiled)
