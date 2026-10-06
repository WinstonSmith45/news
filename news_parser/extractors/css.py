from bs4 import BeautifulSoup

from news_parser.config import ConfigError
from news_parser.extractors.base import ContentExtractor, ContentNotFound, register_extractor
from news_parser.models import NewsItem


@register_extractor
class CssExtractor(ContentExtractor):
    """Скачивает страницу новости и берёт HTML блока по CSS-селектору.

    Параметры: selector — строка или список селекторов (используется первый найденный).
    """

    strategy = "css"
    uses_network = True

    def __init__(self, options, http):
        super().__init__(options, http)
        selector = options.get("selector")
        if not selector:
            raise ConfigError("стратегия css: не задан selector")
        self.selectors = [selector] if isinstance(selector, str) else list(selector)

    def fetch(self, item: NewsItem) -> str:
        if not item.url:
            raise ContentNotFound("у новости нет ссылки на страницу")
        resp = self.http.get(item.url)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding=resp.encoding)
        for selector in self.selectors:
            node = soup.select_one(selector)
            if node is not None:
                return node.decode_contents().strip()
        raise ContentNotFound(f"на странице не найден блок {self.selectors}")
