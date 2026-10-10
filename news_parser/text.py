import re

from bs4 import BeautifulSoup

# После этих тегов ставим перевод строки, чтобы абзацы не слипались.
BLOCK_TAGS = [
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "figure", "figcaption", "table", "tr", "section", "article",
]
SKIP_TAGS = ["script", "style", "noscript", "template", "iframe", "svg"]
# Эмодзи: картинки и флаги, значки (☀ ✅ ⭐), а также служебные символы, из которых они собираются
# (вариант начертания U+FE0F, соединитель U+200D, keycap U+20E3, теги флагов). Обычные символы
# вроде «№», «©», «°», «™» сюда не входят.
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0E\uFE0F\u200D\u20E3\U000E0020-\U000E007F]"
)


def html_to_text(html: str | None) -> str | None:
    """Текст без разметки — для полнотекстового поиска и будущих эмбеддингов."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(SKIP_TAGS):
        tag.decompose()
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_after("\n")
    lines = (re.sub(r"\s+", " ", line).strip() for line in soup.get_text().splitlines())
    text = "\n".join(line for line in lines if line)
    return text or None


def clean_title(title: str | None) -> str | None:
    """Заголовок без эмодзи («🦆 Утку-мандаринку…») и лишних пробелов."""
    if not title:
        return None
    # Неразрывные пробелы (у Медузы, Хабра — «в\xa0полицию») не трогаем, схлопываем только обычные.
    return re.sub(r"[ \t\r\n]+", " ", EMOJI.sub("", title)).strip(" \t\r\n") or None
