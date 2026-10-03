import pytest

from anchor.evals.metrics import (
    contains_fact,
    first_relevant_rank,
    mean_reciprocal_rank,
    occurrences,
    overlaps,
    percentile,
    ratio,
    recall_at,
    values_match,
)


def test_occurrences_finds_every_match() -> None:
    assert occurrences("May 1, 2026 ... May 1, 2026", "May 1, 2026") == [(0, 11), (16, 27)]
    assert occurrences("nothing here", "May 1") == []


def test_overlap_is_strict_about_touching_edges() -> None:
    assert overlaps((0, 10), (5, 15))
    assert not overlaps((0, 10), (10, 20))


@pytest.mark.parametrize(
    ("field", "expected", "actual", "match"),
    [
        ("transaction_amount", "2500000", "2500000", True),
        ("transaction_amount", "2500000", "25000000", False),
        ("report_date", "2026-04-17", "2026-04-17", True),
        ("officer_name", "John Ternus", "Mr. John Ternus", True),
        ("officer_name", "John Ternus", "john ternus.", True),
        ("officer_name", "John Ternus", "Tim Cook", False),
        ("officer_title", "Chief Executive Officer", None, False),
        ("counterparty", "Citibank, N.A.", "Citibank", True),
    ],
)
def test_values_match(field: str, expected: str, actual: str | None, match: bool) -> None:
    assert values_match(field, expected, actual) is match


def test_contains_fact_ignores_case_and_thousands_separators() -> None:
    answer = "Intel agreed to sell 210526315 shares at $95.00 each."

    assert contains_fact(answer, "210,526,315")
    assert contains_fact(answer, "95.00")
    assert not contains_fact(answer, "96.00")
    assert contains_fact("The Executive Chair role.", "executive chair")


def test_ranking_metrics() -> None:
    ranks = [
        first_relevant_rank(h)
        for h in ([False, True], [True], [False, False], [False] * 6 + [True])
    ]

    assert ranks == [2, 1, None, 7]
    assert recall_at(ranks, 5) == 0.5
    assert recall_at(ranks, 10) == 0.75
    assert mean_reciprocal_rank(ranks) == pytest.approx((1 / 2 + 1 + 1 / 7) / 4)
    assert recall_at([], 5) == 0.0


def test_percentile_and_ratio() -> None:
    sample = [float(v) for v in range(1, 101)]

    assert percentile(sample, 50) == 50.0
    assert percentile(sample, 95) == 95.0
    assert percentile([], 95) is None
    assert ratio(1, 3) == 0.3333
    assert ratio(1, 0) is None
