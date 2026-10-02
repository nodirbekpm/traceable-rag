"""What is extracted from an 8-K, and the shape the model must answer in."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "s1"


class Kind(StrEnum):
    MONEY = "money"
    PER_SHARE = "per_share"
    PERCENT = "percent"
    DATE = "date"
    ITEM = "item"
    TEXT = "text"


# field name -> (kind, description shown to the model)
FIELDS: dict[str, tuple[Kind, str]] = {
    "report_date": (Kind.DATE, "Date of report (date of earliest event reported)."),
    "item_number": (Kind.ITEM, "An Item reported in this filing, e.g. 2.02. One fact per Item."),
    "fiscal_period": (Kind.TEXT, "Fiscal period the results refer to, e.g. 'third quarter 2026'."),
    "revenue": (Kind.MONEY, "Total revenue / net sales for the reported period."),
    "net_income": (Kind.MONEY, "Net income (or loss) for the reported period."),
    "eps_diluted": (Kind.PER_SHARE, "Diluted earnings per share for the reported period."),
    "dividend_per_share": (Kind.PER_SHARE, "Declared cash dividend per share."),
    "transaction_amount": (Kind.MONEY, "Value of an agreement, acquisition, financing or award."),
    "counterparty": (Kind.TEXT, "Other party to a material agreement or transaction."),
    "agreement_date": (Kind.DATE, "Date an agreement was entered into, amended or terminated."),
    "officer_name": (Kind.TEXT, "Director or officer who was appointed, resigned or departed."),
    "officer_title": (Kind.TEXT, "Title of that director or officer."),
    "officer_change_type": (Kind.TEXT, "What happened: appointed, resigned, retired, terminated."),
    "officer_effective_date": (Kind.DATE, "Date the officer change takes effect."),
}

FieldName = Literal[
    "report_date",
    "item_number",
    "fiscal_period",
    "revenue",
    "net_income",
    "eps_diluted",
    "dividend_per_share",
    "transaction_amount",
    "counterparty",
    "agreement_date",
    "officer_name",
    "officer_title",
    "officer_change_type",
    "officer_effective_date",
]


class FactOut(BaseModel):
    field: FieldName
    value: str = Field(description="The value exactly as written in the document.")
    quote: str = Field(
        description="A verbatim passage copied from the document that contains the value."
    )
    entity: str | None = Field(
        default=None,
        description="Who or what the value is about when a filing has several, "
        "e.g. the officer's name for officer_* fields.",
    )
    confidence: float = Field(ge=0, le=1)


class ExtractionOut(BaseModel):
    facts: list[FactOut]
