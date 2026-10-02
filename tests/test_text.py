from anchor.text import html_to_text


def test_block_elements_become_lines_and_whitespace_is_collapsed() -> None:
    html = b"<html><body><p>Item 2.02   Results</p><div>Revenue was\n  $4.2&nbsp;million.</div></body></html>"

    assert html_to_text(html) == "Item 2.02 Results\n\nRevenue was\n$4.2 million."


def test_invisible_content_is_dropped() -> None:
    html = (
        b"<html><head><title>8-K</title><style>p{color:red}</style></head><body>"
        b"<ix:header><ix:hidden>0000320193</ix:hidden></ix:header>"
        b'<div style="display:none">hidden <div>nested</div> still hidden</div>'
        b"<script>var x = 1;</script><p>Visible</p></body></html>"
    )

    assert html_to_text(html) == "Visible"


def test_unclosed_tags_inside_hidden_block_do_not_swallow_the_document() -> None:
    html = b'<div style="display:none"><p>hidden<br><span>x</div><p>After</p>'

    assert html_to_text(html) == "After"


def test_table_cells_are_separated() -> None:
    html = b"<table><tr><td>Revenue</td><td>$94.9 billion</td></tr><tr><td>EPS</td><td>$1.64</td></tr></table>"

    assert html_to_text(html) == "Revenue $94.9 billion\n\nEPS $1.64"


def test_entities_and_windows_1252_bytes_are_decoded() -> None:
    html = b"<p>AT&amp;T\x92s board &#8212; approved</p>"

    assert html_to_text(html) == "AT&T’s board — approved"


def test_conversion_is_deterministic() -> None:
    html = b"<div><p>One</p><p>Two</p></div>"

    assert html_to_text(html) == html_to_text(html)
