import re

from bs4 import BeautifulSoup

# После этих тегов ставим перевод строки, чтобы абзацы не слипались.
BLOCK_TAGS = [
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "figure", "figcaption", "table", "tr", "section", "article",
]
SKIP_TAGS = ["script", "style", "noscript", "template", "iframe", "svg"]


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
