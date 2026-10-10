import re
from typing import Any

import soupsieve
from bs4 import BeautifulSoup, Comment, Tag

from news_parser.config import ConfigError

# Блоки, которые удаляются опцией drop_link_only.
LINK_ONLY_TAGS = ["p", "li"]
# Блоки, которые удаляются опцией drop_text.
DROP_TEXT_TAGS = ["p", "li"]
# Значимый текст — хотя бы одна буква или цифра (пробелы, пунктуация и эмодзи вроде «➡» не в счёт).
MEANINGFUL = re.compile(r"\w")


class Cleaner:
    """Удаляет мусор из HTML полного текста; применяется после любой стратегии.

    Параметры (в секции content источника):
      exclude        — CSS-селектор или список селекторов: удалить совпавшие элементы;
      drop_link_only — удалить абзацы, весь текст которых — ссылки («читайте также» и т.п.);
      drop_text      — регулярное выражение или список: удалить абзацы, в тексте которых оно найдено
                       (re.search; «^» — начало абзаца, например подписи «^Фото: »);
      drop_before    — {target, text_in}: удалить идущие подряд прямо перед элементом target блоки,
                       весь текст которых внутри text_in (например, жирные подзаголовки перед виджетом).
    """

    def __init__(self, options: dict[str, Any]):
        exclude = options.get("exclude") or []
        self.exclude = [exclude] if isinstance(exclude, str) else list(exclude)
        for selector in self.exclude:
            try:
                soupsieve.compile(selector)
            except Exception as e:  # soupsieve бросает и SelectorSyntaxError, и NotImplementedError
                raise ConfigError(f"exclude: некорректный селектор {selector!r}: {e}") from None
        self.drop_link_only = options.get("drop_link_only", False)
        if not isinstance(self.drop_link_only, bool):
            raise ConfigError("drop_link_only должен быть true или false")
        drop_text = options.get("drop_text") or []
        drop_text = [drop_text] if isinstance(drop_text, str) else list(drop_text)
        self.drop_text = []
        for pattern in drop_text:
            try:
                self.drop_text.append(re.compile(pattern))
            except (re.error, TypeError) as e:
                raise ConfigError(f"drop_text: некорректное регулярное выражение {pattern!r}: {e}") from None
        drop_before = options.get("drop_before") or {}
        if drop_before:
            if not isinstance(drop_before, dict) or not drop_before.get("target") or not drop_before.get("text_in"):
                raise ConfigError("drop_before: нужны target и text_in")
            for key in ("target", "text_in"):
                try:
                    soupsieve.compile(drop_before[key])
                except Exception as e:
                    raise ConfigError(f"drop_before.{key}: некорректный селектор {drop_before[key]!r}: {e}") from None
        self.drop_before = drop_before

    @property
    def enabled(self) -> bool:
        return bool(self.exclude) or self.drop_link_only or bool(self.drop_text) or bool(self.drop_before)

    def clean(self, html: str) -> str:
        if not self.enabled:
            return html
        soup = BeautifulSoup(html, "lxml")
        root = soup.body or soup
        removed = 0
        # До exclude: целевые элементы могут удаляться и им.
        if self.drop_before:
            removed += drop_blocks_before(root, self.drop_before["target"], self.drop_before["text_in"])
        # Сначала находим совпадения по всем селекторам, потом удаляем: иначе удаление
        # по одному селектору ломает другие (например, "h4:has(+ ul)" и "h4 + ul").
        matched = [el for selector in self.exclude for el in root.select(selector)]
        for el in matched:
            if not el.decomposed:
                el.decompose()
                removed += 1
        if self.drop_text:
            removed += drop_text_blocks(root, self.drop_text)
        if self.drop_link_only:
            removed += drop_link_only_blocks(root)
        # Ничего не удалили — отдаём исходный HTML, а не пересобранный парсером.
        if not removed:
            return html
        return root.decode_contents().strip()


def drop_link_only_blocks(node: Tag) -> int:
    removed = 0
    for block in node.find_all(LINK_ONLY_TAGS):
        # Блок мог уже удалиться вместе с родителем (p внутри li).
        if block.decomposed:
            continue
        if is_link_only(block):
            block.decompose()
            removed += 1
    return removed


def drop_text_blocks(node: Tag, patterns: list[re.Pattern]) -> int:
    removed = 0
    for block in node.find_all(DROP_TEXT_TAGS):
        # Блок мог уже удалиться вместе с родителем (p внутри li).
        if block.decomposed:
            continue
        text = block.get_text().strip()
        if any(pattern.search(text) for pattern in patterns):
            block.decompose()
            removed += 1
    return removed


def is_link_only(block: Tag) -> bool:
    has_link_text = False
    for string in block.find_all(string=True):
        if isinstance(string, Comment) or not MEANINGFUL.search(string):
            continue
        if string.find_parent("a") is None:
            return False
        has_link_text = True
    return has_link_text


def drop_blocks_before(node: Tag, target: str, text_in: str) -> int:
    removed = 0
    for el in node.select(target):
        prev = el.find_previous_sibling()
        while prev is not None and is_text_within(prev, text_in):
            current, prev = prev, prev.find_previous_sibling()
            current.decompose()
            removed += 1
    return removed


def is_text_within(block: Tag, selector: str) -> bool:
    """Весь значимый текст блока лежит внутри элементов, подходящих под selector (и он есть)."""
    inner = {id(el) for el in block.select(selector)}
    has_text = False
    for string in block.find_all(string=True):
        if isinstance(string, Comment) or not MEANINGFUL.search(string):
            continue
        if not any(id(parent) in inner for parent in string.parents):
            return False
        has_text = True
    return has_text
