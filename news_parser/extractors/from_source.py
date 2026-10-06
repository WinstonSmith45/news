from news_parser.extractors.base import ContentExtractor, ContentNotFound, register_extractor
from news_parser.models import NewsItem


@register_extractor
class FromSourceExtractor(ContentExtractor):
    """Полный текст уже пришёл вместе с новостью (content:encoded в RSS, текст поста в Telegram)."""

    strategy = "from_source"

    def fetch(self, item: NewsItem) -> str:
        if not item.content_html:
            raise ContentNotFound("источник не отдал полный текст")
        return item.content_html
