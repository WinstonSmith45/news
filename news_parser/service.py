import logging
import threading
import time
from dataclasses import dataclass

from news_parser.categories import CategoryFetcher
from news_parser.config import SourceConfig
from news_parser.extractors import ContentExtractor, ContentNotFound
from news_parser.http_client import HttpError
from news_parser.models import ContentStatus, NewsItem
from news_parser.sources import Source
from news_parser.storage import Storage
from news_parser.text import html_to_text

logger = logging.getLogger(__name__)


def is_skipped(config: SourceConfig, item: NewsItem) -> bool:
    """Новость не нужна: ссылка подходит под skip_urls, есть рубрика из skip_categories
    или нет ни одной рубрики из only_categories."""
    if item.url and any(p.search(item.url) for p in config.skip_urls):
        return True
    if config.skip_categories and any(c.strip().casefold() in config.skip_categories for c in item.categories):
        return True
    if config.only_categories:
        return not any(c.strip().casefold() in config.only_categories for c in item.categories)
    return False


class ShutdownRequested(Exception):
    pass


def make_interruptible_sleep(stop_event: threading.Event):
    """sleep(), который прерывается исключением ShutdownRequested при остановке сервиса."""

    def sleep(seconds: float) -> None:
        if stop_event.wait(seconds):
            raise ShutdownRequested()

    return sleep


@dataclass
class SourceRunner:
    config: SourceConfig
    source: Source
    extractor: ContentExtractor
    categories: CategoryFetcher | None = None


class Service:
    def __init__(
        self,
        runners: list[SourceRunner],
        storage: Storage,
        stop_event: threading.Event,
        request_delay: float,
        content_max_cycles: int,
    ):
        self._runners = runners
        self._storage = storage
        self._stop = stop_event
        self._sleep = make_interruptible_sleep(stop_event)
        self._request_delay = request_delay
        self._content_max_cycles = content_max_cycles

    def run(self) -> None:
        if not self._runners:
            logger.error("нет включённых источников, сервис завершается")
            return
        logger.info("сервис запущен, источников: %d", len(self._runners))
        next_run = {r.config.id: time.monotonic() for r in self._runners}
        try:
            while not self._stop.is_set():
                for runner in self._runners:
                    if self._stop.is_set():
                        break
                    if time.monotonic() >= next_run[runner.config.id]:
                        self._run_source(runner)
                        next_run[runner.config.id] = time.monotonic() + runner.config.interval
                timeout = max(0.0, min(next_run.values()) - time.monotonic())
                self._stop.wait(timeout)
        except ShutdownRequested:
            pass
        logger.info("сервис остановлен")

    def _run_source(self, runner: SourceRunner) -> None:
        source_id = runner.config.id
        started = time.monotonic()
        try:
            # Сначала — новости, у которых текст не удалось получить в прошлых циклах.
            retried = self._retry_pending(runner)

            state = self._storage.get_state(source_id)
            result = runner.source.fetch(state)

            # Убираем дубли внутри выдачи, ненужное (skip_urls, skip_categories, only_categories) и то, что уже есть в базе.
            unique = list({item.external_id: item for item in result.items}.values())
            wanted = [i for i in unique if not is_skipped(runner.config, i)]
            skipped = len(unique) - len(wanted)
            if skipped:
                logger.debug("%s: пропущено фильтрами: %d", source_id, skipped)
            unique = wanted
            existing = self._storage.existing_ids(source_id, [i.external_id for i in unique])
            new_items = [i for i in unique if i.external_id not in existing]

            stats = {ContentStatus.OK: 0, ContentStatus.PENDING: 0, ContentStatus.FAILED: 0}
            for item in new_items:
                self._fetch_categories(runner, item)
                content, status, error = self._extract(runner, item, attempt=1)
                if content is not None:
                    item.content_html = content
                item.content_text = html_to_text(item.content_html)
                if self._storage.insert(item, status, error):
                    stats[status] += 1

            self._storage.save_state(
                source_id,
                result.state,
                {
                    "fetched": len(result.items), "skipped": skipped, "new": len(new_items),
                    **stats, "retried": retried,
                },
            )
            logger.info(
                "%s: получено %d, новых %d (текст: ok=%d, pending=%d, failed=%d), повторов pending: %d, %.1f с",
                source_id, len(result.items), len(new_items), stats[ContentStatus.OK],
                stats[ContentStatus.PENDING], stats[ContentStatus.FAILED], retried,
                time.monotonic() - started,
            )
        except ShutdownRequested:
            raise
        except Exception:
            logger.exception("%s: ошибка при обработке источника", source_id)

    def _retry_pending(self, runner: SourceRunner) -> int:
        pending = self._storage.pending(runner.config.id)
        for record_id, attempts, item in pending:
            content, status, error = self._extract(runner, item, attempt=attempts + 1)
            self._storage.update_content(
                record_id, content, html_to_text(content), status, error
            )
        return len(pending)

    def _fetch_categories(self, runner: SourceRunner, item: NewsItem) -> None:
        """Дополнить рубрики со страницы новости. Ошибка не мешает сохранить новость."""
        if runner.categories is None:
            return
        if self._stop.is_set():
            raise ShutdownRequested()
        self._sleep(self._request_delay)
        try:
            runner.categories.fetch(item)
        except ShutdownRequested:
            raise
        except Exception as e:
            logger.warning("%s: не удалось получить рубрики %s: %s", runner.config.id, item.url, e)

    def _extract(
        self, runner: SourceRunner, item: NewsItem, attempt: int
    ) -> tuple[str | None, str, str | None]:
        """Получить полный текст. Возвращает (html, статус, ошибка)."""
        if self._stop.is_set():
            raise ShutdownRequested()
        if runner.extractor.uses_network:
            self._sleep(self._request_delay)
        try:
            return runner.extractor.extract(item), ContentStatus.OK, None
        except ShutdownRequested:
            raise
        except ContentNotFound as e:
            error, transient = str(e), False
        except HttpError as e:
            error, transient = str(e), e.transient
        except Exception as e:
            logger.exception("%s: ошибка извлечения текста %s", runner.config.id, item.url)
            error, transient = f"{type(e).__name__}: {e}", True

        logger.warning("%s: не удалось получить текст %s: %s", runner.config.id, item.url, error)
        if transient and attempt < self._content_max_cycles:
            return None, ContentStatus.PENDING, error
        return None, ContentStatus.FAILED, error
