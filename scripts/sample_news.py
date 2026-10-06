"""Выгрузить N случайных новостей (url, title, content_text, categories) в текстовый файл.

Подключение — из DATABASE_URL, как у парсера.

    python scripts/sample_news.py [файл] [-n 20]    # «-» вместо файла — вывод в stdout
"""

import argparse
import os
import sys

import psycopg

SEPARATOR = "=" * 80


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", nargs="?", default="sample_news.txt", help="файл результата, «-» — stdout")
    parser.add_argument("-n", type=int, default=20, help="сколько новостей выбрать (по умолчанию 20)")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL", "postgresql://news@localhost:5432/news")
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT url, title, content_text, categories FROM news ORDER BY random() LIMIT %s",
            (args.n,),
        ).fetchall()

    out = sys.stdout if args.output == "-" else open(args.output, "w", encoding="utf-8")
    try:
        for i, (url, title, content_text, categories) in enumerate(rows, 1):
            out.write(f"{SEPARATOR}\n#{i}\n")
            out.write(f"URL: {url or ''}\n")
            out.write(f"Заголовок: {title or ''}\n")
            out.write(f"Категории: {', '.join(categories)}\n")
            out.write(f"Текст:\n{content_text or '(нет текста)'}\n\n")
    finally:
        if out is not sys.stdout:
            out.close()

    if out is not sys.stdout:
        print(f"сохранено новостей: {len(rows)} → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
