from anchor.extraction.provenance import locate
from anchor.extraction.schema import FactOut
from anchor.extraction.validator import validate

TEXT = (
    "Item 2.02 Results of Operations and Financial Condition.\n\n"
    "On May 1, 2026, Example Corp reported revenue of $4.2 million for the quarter, "
    "and diluted earnings per share of $1.64.\n\n"
    "The company’s board declared a dividend."
)


def fact(**overrides) -> FactOut:
    fields = {
        "field": "revenue",
        "value": "$4.2 million",
        "quote": "reported revenue of $4.2 million for the quarter",
        "confidence": 0.95,
    }
    return FactOut(**(fields | overrides))


def test_verified_fact_points_at_the_value_itself() -> None:
    result = validate(fact(), TEXT)

    assert result.validation_status == "verified"
    assert TEXT[result.span_start : result.span_end] == "$4.2 million"
    assert result.source_excerpt == "reported revenue of $4.2 million for the quarter"
    assert (result.value_normalized, result.unit) == ("4200000", "USD")
    assert result.confidence == 0.95


def test_quote_absent_from_source_is_a_hallucination() -> None:
    result = validate(fact(quote="reported revenue of $4.2 million for the full year"), TEXT)

    assert result.validation_status == "hallucinated"
    assert result.span_start is None
    assert result.confidence == 0.0


def test_value_that_differs_from_its_quote_is_a_hallucination() -> None:
    result = validate(fact(value="$4.3 million"), TEXT)

    assert result.validation_status == "hallucinated"
    assert result.reason == "value not found inside its quote"
    assert result.span_start is None


def test_value_present_elsewhere_but_not_in_the_quote_is_a_hallucination() -> None:
    result = validate(fact(field="eps_diluted", value="$1.64"), TEXT)

    assert result.validation_status == "hallucinated"


def test_whitespace_and_quote_style_differences_still_match_with_a_penalty() -> None:
    result = validate(
        fact(
            field="counterparty",
            value="The company's board",
            quote="The company's   board declared a dividend.",
            confidence=1.0,
        ),
        TEXT,
    )

    assert result.validation_status == "verified"
    assert result.confidence == 0.9
    assert TEXT[result.span_start : result.span_end] == "The company’s board"


def test_located_but_unparseable_value_is_rejected_and_keeps_its_span() -> None:
    result = validate(fact(field="report_date", value="revenue", quote="reported revenue of"), TEXT)

    assert result.validation_status == "rejected"
    assert TEXT[result.span_start : result.span_end] == "revenue"


def test_low_confidence_goes_to_review() -> None:
    result = validate(fact(confidence=0.5), TEXT)

    assert result.validation_status == "needs_review"
    assert result.span_start is not None


def test_implausibly_large_amount_is_rejected() -> None:
    text = "revenue of $99,000 trillion"

    result = validate(fact(value="$99,000 trillion", quote=text), text)

    assert result.validation_status == "rejected"
    assert result.reason == "value outside the plausible range"


def test_locate_searches_only_inside_the_given_window() -> None:
    first = TEXT.index("May 1, 2026")

    assert locate(TEXT, "May 1, 2026", start=first + 1) is None
    assert locate(TEXT, "  ") is None
