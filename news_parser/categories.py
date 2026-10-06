from typing import Any

from bs4 import BeautifulSoup

from news_parser.config import ConfigError
from news_parser.http_client import HttpClient
from news_parser.models import NewsItem


class CategoryFetcher:
    """Скачивает страницу новости и добавляет рубрики, найденные по CSS-селектору, в item.categories.

    Параметры: selector — строка или список селекторов (берутся все найденные элементы).
    Значение элемента — атрибут content (для <meta>), иначе его текст.
    """

    def __init__(self, options: dict[str, Any], http: HttpClient):
        selector = options.get("selector")
        if not selector:
            raise ConfigError("categories: не задан selector")
        self.selectors = [selector] if isinstance(selector, str) else list(selector)
        self.http = http

    def fetch(self, item: NewsItem) -> None:
        if not item.url:
            return
        resp = self.http.get(item.url)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding=resp.encoding)
        for selector in self.selectors:
            for node in soup.select(selector):
                value = (node.get("content") or node.get_text()).strip()
                if value and value not in item.categories:
                    item.categories.append(value)


def create_category_fetcher(source_id: str, options: dict[str, Any], http: HttpClient) -> CategoryFetcher | None:
    if not options:
        return None
    try:
        return CategoryFetcher(options, http)
    except ConfigError as e:
        raise ConfigError(f"источник {source_id}: {e}") from None
