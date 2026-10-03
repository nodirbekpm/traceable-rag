"""Turn values as written ("$4.2M", "May 1, 2026") into one canonical form per kind."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from anchor.extraction.schema import Kind


class NormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class Normalized:
    value: str
    unit: str | None = None


_SCALES = {
    "thousand": 10**3,
    "k": 10**3,
    "million": 10**6,
    "m": 10**6,
    "mm": 10**6,
    "billion": 10**9,
    "b": 10**9,
    "bn": 10**9,
    "trillion": 10**12,
}
_MONEY = re.compile(
    r"""^(?P<open>\()?\s*(?P<minus>-)?\s*
        (?P<prefix>US\$|\$|USD)?\s*
        (?P<number>\d[\d,]*(?:\.\d+)?)\s*
        (?P<scale>thousand|million|billion|trillion|mm|bn|k|m|b)?\s*
        (?P<suffix>USD|US\ dollars|dollars)?\s*
        (?P<close>\))?$""",
    re.IGNORECASE | re.VERBOSE,
)
_PER_SHARE = re.compile(
    r"^(?P<open>\()?\s*(?P<minus>-)?\s*\$?\s*(?P<number>\d+(?:\.\d+)?)\s*\)?"
    r"(?:\s*(?:per|a)\s+(?:diluted\s+|basic\s+)?share)?$",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"^(?P<number>-?\d[\d,]*(?:\.\d+)?)\s*(?:%|percent)$", re.IGNORECASE)
_ITEM = re.compile(r"^(?:Item\s+)?(?P<number>\d\.\d{2})\.?$", re.IGNORECASE)
_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%b. %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %B %Y")


def _decimal(number: str) -> Decimal:
    try:
        return Decimal(number.replace(",", ""))
    except InvalidOperation as exc:
        raise NormalizationError(f"not a number: {number!r}") from exc


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _money(raw: str) -> Normalized:
    match = _MONEY.match(raw)
    if match is None:
        raise NormalizationError(f"not a money amount: {raw!r}")
    # A bare number is ambiguous (shares? thousands?), so a currency or scale must be present.
    if not (match["prefix"] or match["suffix"] or match["scale"]):
        raise NormalizationError(f"money amount without currency or scale: {raw!r}")
    amount = _decimal(match["number"]) * _SCALES.get((match["scale"] or "").lower(), 1)
    if match["open"] or match["minus"]:
        amount = -amount
    return Normalized(_plain(amount), "USD")


def _per_share(raw: str) -> Normalized:
    match = _PER_SHARE.match(raw)
    if match is None:
        raise NormalizationError(f"not a per-share amount: {raw!r}")
    amount = _decimal(match["number"])
    if match["open"] or match["minus"]:
        amount = -amount
    return Normalized(_plain(amount), "USD/share")


def _percent(raw: str) -> Normalized:
    match = _PERCENT.match(raw)
    if match is None:
        raise NormalizationError(f"not a percentage: {raw!r}")
    return Normalized(_plain(_decimal(match["number"])), "%")


def _date(raw: str) -> Normalized:
    for fmt in _DATE_FORMATS:
        try:
            return Normalized(datetime.strptime(raw, fmt).date().isoformat())
        except ValueError:
            continue
    raise NormalizationError(f"not a recognised date: {raw!r}")


def _item(raw: str) -> Normalized:
    match = _ITEM.match(raw)
    if match is None:
        raise NormalizationError(f"not an Item number: {raw!r}")
    return Normalized(match["number"])


def _text(raw: str) -> Normalized:
    if not raw:
        raise NormalizationError("empty value")
    return Normalized(raw)


_NORMALIZERS = {
    Kind.MONEY: _money,
    Kind.PER_SHARE: _per_share,
    Kind.PERCENT: _percent,
    Kind.DATE: _date,
    Kind.ITEM: _item,
    Kind.TEXT: _text,
}


def normalize(kind: Kind, raw: str) -> Normalized:
    return _NORMALIZERS[kind](" ".join(raw.split()))
