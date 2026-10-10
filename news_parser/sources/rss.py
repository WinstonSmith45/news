import calendar
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

from news_parser.models import NewsItem
from news_parser.sources.base import FetchResult, Source, register_source
from news_parser.text import clean_title

logger = logging.getLogger(__name__)

TRACKING_PARAM_PREFIXES = ("utm_",)


def normalize_url(url: str) -> str:
    """Убрать трекинговые параметры и якорь, чтобы одна статья не дублировалась."""
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(TRACKING_PARAM_PREFIXES)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _to_datetime(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    # feedparser отдаёт время уже в UTC.
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


@register_source
class RssSource(Source):
    """Параметры в sources.yaml: url — адрес RSS/Atom-ленты."""

    type = "rss"

    def fetch(self, state: dict[str, Any]) -> FetchResult:
        url = self.option("url")
        resp = self.http.get(url)
        feed = feedparser.parse(
            resp.content, response_headers={"content-type": resp.headers.get("Content-Type", "")}
        )
        if feed.bozo and not feed.entries:
            raise ValueError(f"не удалось разобрать ленту {url}: {feed.bozo_exception}")

        items = []
        for entry in feed.entries:
            item = self._to_item(entry)
            if item is None:
                logger.warning("%s: пропущена запись без ссылки и guid: %s", self.id, entry.get("title"))
                continue
            items.append(item)
        return FetchResult(items=items, state=state)

    def _to_item(self, entry: Any) -> NewsItem | None:
        link = normalize_url(entry["link"]) if entry.get("link") else None
        external_id = link or entry.get("id")
        if not external_id:
            return None
        # content:encoded — полный текст, если лента его отдаёт.
        content = entry["content"][0].get("value") if entry.get("content") else None
        return NewsItem(
            source_id=self.id,
            source_type=self.type,
            external_id=external_id,
            url=link,
            title=clean_title(entry.get("title")),
            content_html=content or None,
            categories=[t["term"] for t in entry.get("tags", []) if t.get("term")],
            published_at=_to_datetime(entry),
        )
