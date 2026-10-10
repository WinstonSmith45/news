"""Пробный прогон источника: разобрать ленту и получить текст так же, как сервис, но без записи в базу.

Источник берётся из sources.yaml (или SOURCES_FILE), в том числе выключенный (enabled: false) —
так проверяются кандидаты перед подключением. Результат — все поля таблицы news для каждой
новости — сохраняется в текстовый файл.

    PYTHONPATH=. .venv/bin/python scripts/preview_source.py knife preview_knife.txt [-n 10]
"""

import argparse
import sys
import time

from news_parser.categories import create_category_fetcher
from news_parser.config import ConfigError, Settings, load_sources
from news_parser.extractors import ContentNotFound, create_extractor
from news_parser.http_client import HttpClient, HttpError
from news_parser.models import ContentStatus
from news_parser.service import is_skipped
from news_parser.sources import create_source
from news_parser.text import html_to_text

SEPARATOR = "=" * 80


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source_id", help="id источника в sources.yaml")
    parser.add_argument("output", help="файл результата, «-» — stdout")
    parser.add_argument("-n", type=int, help="обработать только первые N новостей ленты")
    args = parser.parse_args()

    settings = Settings.from_env()
    try:
        configs = {c.id: c for c in load_sources(settings.sources_file, settings.default_interval)}
        cfg = configs.get(args.source_id)
        if cfg is None:
            raise ConfigError(f"в {settings.sources_file} нет источника {args.source_id!r}, есть: {', '.join(configs)}")
        http = HttpClient(
            timeout=settings.http_timeout,
            max_attempts=settings.http_max_attempts,
            backoff_base=settings.http_backoff_base,
            backoff_max=settings.http_backoff_max,
            sleep=time.sleep,
        )
        source = create_source(cfg, http)
        extractor = create_extractor(cfg.id, cfg.content, http)
        categories = create_category_fetcher(cfg.id, cfg.categories, http)
    except ConfigError as e:
        print(f"ошибка конфигурации: {e}", file=sys.stderr)
        return 2

    items = source.fetch({}).items
    # Как в сервисе: дубли внутри выдачи и отфильтрованное (skip_urls, skip_categories, only_categories) отбрасываются.
    items = list({i.external_id: i for i in items}.values())
    skipped = [i for i in items if is_skipped(cfg, i)]
    items = [i for i in items if i not in skipped][: args.n]

    output = args.output
    out = sys.stdout if output == "-" else open(output, "w", encoding="utf-8")
    stats = {ContentStatus.OK: 0, ContentStatus.FAILED: 0}
    try:
        for n, item in enumerate(items, 1):
            print(f"[{n}/{len(items)}] {item.url}", file=sys.stderr)
            if categories is not None:
                time.sleep(settings.request_delay)
                try:
                    categories.fetch(item)
                except Exception as e:
                    print(f"  рубрики: {e}", file=sys.stderr)
            if extractor.uses_network:
                time.sleep(settings.request_delay)
            status, error = ContentStatus.OK, None
            try:
                item.content_html = extractor.extract(item)
            except (ContentNotFound, HttpError) as e:
                # Сервис при временной ошибке поставил бы pending и повторил позже.
                status, error = ContentStatus.FAILED, str(e)
            item.content_text = html_to_text(item.content_html)
            stats[status] += 1

            out.write(f"{SEPARATOR}\n#{n}\n")
            for field in ("source_id", "source_type", "external_id", "url", "title", "published_at"):
                out.write(f"{field}: {getattr(item, field) or ''}\n")
            out.write(f"categories: {', '.join(item.categories)}\n")
            out.write(f"content_status: {status}\n")
            if error:
                out.write(f"content_error: {error}\n")
            out.write(f"--- content_text ---\n{item.content_text or ''}\n")
            out.write(f"--- content_html ---\n{item.content_html or ''}\n\n")
    finally:
        if out is not sys.stdout:
            out.close()

    print(
        f"новостей: {len(items)} (ok={stats[ContentStatus.OK]}, failed={stats[ContentStatus.FAILED]}), "
        f"пропущено фильтрами: {len(skipped)} → {output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
