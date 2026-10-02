import pytest

from anchor.extraction.normalize import NormalizationError, Normalized, normalize
from anchor.extraction.schema import Kind


@pytest.mark.parametrize(
    "raw",
    [
        "$4.2M",
        "4,200,000 USD",
        "$4.2 million",
        "US$4,200,000",
        "4.2 million dollars",
        "$4,200,000.00",
    ],
)
def test_money_spellings_collapse_to_one_form(raw: str) -> None:
    assert normalize(Kind.MONEY, raw) == Normalized("4200000", "USD")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$94.9 billion", "94900000000"),
        ("$1.5 thousand", "1500"),
        ("($3.1 million)", "-3100000"),
        ("-$250", "-250"),
        ("$0.5", "0.5"),
    ],
)
def test_money_scales_and_signs(raw: str, expected: str) -> None:
    assert normalize(Kind.MONEY, raw).value == expected


@pytest.mark.parametrize("raw", ["4,200,000", "about $4 million", "$", "four million dollars"])
def test_ambiguous_money_is_rejected(raw: str) -> None:
    with pytest.raises(NormalizationError):
        normalize(Kind.MONEY, raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1.64", "1.64"), ("1.64", "1.64"), ("($0.12)", "-0.12"), ("$0.250", "0.25")],
)
def test_per_share(raw: str, expected: str) -> None:
    assert normalize(Kind.PER_SHARE, raw) == Normalized(expected, "USD/share")


@pytest.mark.parametrize(
    "raw", ["May 1, 2026", "May  1, 2026", "2026-05-01", "05/01/2026", "1 May 2026", "May 01, 2026"]
)
def test_date_spellings_collapse_to_iso(raw: str) -> None:
    assert normalize(Kind.DATE, raw) == Normalized("2026-05-01")


def test_impossible_date_is_rejected() -> None:
    with pytest.raises(NormalizationError):
        normalize(Kind.DATE, "February 30, 2026")


@pytest.mark.parametrize(("raw", "expected"), [("12%", "12"), ("7.5 percent", "7.5")])
def test_percent(raw: str, expected: str) -> None:
    assert normalize(Kind.PERCENT, raw) == Normalized(expected, "%")


@pytest.mark.parametrize("raw", ["2.02", "Item 2.02", "item 5.02."])
def test_item_number(raw: str) -> None:
    assert normalize(Kind.ITEM, raw).value in {"2.02", "5.02"}


def test_item_number_rejects_free_text() -> None:
    with pytest.raises(NormalizationError):
        normalize(Kind.ITEM, "Results of Operations")
