import logging
import signal
import sys
import threading

from news_parser.categories import create_category_fetcher
from news_parser.config import ConfigError, Settings, load_sources
from news_parser.extractors import create_extractor
from news_parser.http_client import HttpClient
from news_parser.service import Service, SourceRunner, make_interruptible_sleep
from news_parser.sources import create_source
from news_parser.storage import PostgresStorage

logger = logging.getLogger("news_parser")


def main() -> int:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stop_event = threading.Event()

    def handle_signal(signum, _frame):
        logger.info("получен сигнал %s, останавливаемся", signal.Signals(signum).name)
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    http = HttpClient(
        timeout=settings.http_timeout,
        max_attempts=settings.http_max_attempts,
        backoff_base=settings.http_backoff_base,
        backoff_max=settings.http_backoff_max,
        sleep=make_interruptible_sleep(stop_event),
    )

    try:
        configs = load_sources(settings.sources_file, settings.default_interval)
        runners = [
            SourceRunner(
                cfg,
                create_source(cfg, http),
                create_extractor(cfg.id, cfg.content, http),
                create_category_fetcher(cfg.id, cfg.categories, http),
            )
            for cfg in configs
            if cfg.enabled
        ]
    except (ConfigError, OSError) as e:
        logger.error("ошибка конфигурации источников: %s", e)
        return 2

    storage = PostgresStorage(settings.database_url)
    try:
        storage.ensure_schema()
        Service(
            runners,
            storage,
            stop_event,
            request_delay=settings.request_delay,
            content_max_cycles=settings.content_max_cycles,
        ).run()
    finally:
        storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
