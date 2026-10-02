"""Deterministic HTML -> text conversion.

Every span in the system is a pair of character offsets into the text produced
here. The conversion must therefore be stable: any change to its output is a new
`TEXT_VERSION`, and spans recorded under an older version stay tied to it.
"""

import re
from html.parser import HTMLParser

TEXT_VERSION = "t1"

# Content that is never visible to a reader. `ix:header` holds inline-XBRL metadata.
_INVISIBLE_TAGS = {"script", "style", "head", "title", "ix:header"}
_LINE_BREAK_TAGS = {"br", "hr"}
_BLOCK_TAGS = {
    "address", "article", "blockquote", "center", "div", "dd", "dl", "dt", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "ol", "p", "pre", "section",
    "table", "tr", "ul",
}  # fmt: skip
_CELL_TAGS = {"td", "th"}
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none", re.IGNORECASE)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        # While inside an invisible element we only count that element's own tag,
        # so unbalanced markup inside it cannot swallow the rest of the document.
        self._hidden_tag: str | None = None
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._hidden_tag is not None:
            if tag == self._hidden_tag:
                self._hidden_depth += 1
            return
        style = next((value or "" for name, value in attrs if name == "style"), "")
        if tag in _INVISIBLE_TAGS or _HIDDEN_STYLE.search(style):
            self._hidden_tag, self._hidden_depth = tag, 1
        elif tag in _LINE_BREAK_TAGS or tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in _CELL_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._hidden_tag is not None:
            if tag == self._hidden_tag:
                self._hidden_depth -= 1
                if self._hidden_depth == 0:
                    self._hidden_tag = None
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in _CELL_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._hidden_tag is None:
            self.parts.append(data)


def decode(raw: bytes) -> str:
    """EDGAR documents are UTF-8 or, for older filers, Windows-1252."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def html_to_text(raw: bytes) -> str:
    parser = _TextExtractor()
    parser.feed(decode(raw))
    parser.close()
    text = "".join(parser.parts).replace("\r", "\n")
    # Non-breaking and other Unicode spaces become plain spaces so that
    # "$4.2\xa0million" in the source matches "$4.2 million" from a model.
    text = re.sub(r"[^\S\n]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
