"""What is extracted from a document, and the shape the model must answer in.

Two profiles: SEC 8-K filings, and any other document a user uploads.
"""

from dataclasses import dataclass
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


# Fields for any business document: contracts, reports, letters, policies, invoices.
GENERIC_FIELDS: dict[str, tuple[Kind, str]] = {
    "document_date": (Kind.DATE, "Date the document was issued, signed or published."),
    "effective_date": (Kind.DATE, "Date something takes effect; say what in entity."),
    "deadline": (Kind.DATE, "A due, expiry, maturity or termination date; say what in entity."),
    "monetary_amount": (Kind.MONEY, "An amount of money; say what it is in entity."),
    "percentage": (Kind.PERCENT, "A rate, share or percentage; say what it is in entity."),
    "party": (Kind.TEXT, "An organisation involved: party, issuer, buyer, lender, regulator."),
    "person": (Kind.TEXT, "A named person; put their role in entity."),
    "location": (Kind.TEXT, "A place that matters to the document: site, jurisdiction, address."),
    "duration": (Kind.TEXT, "A period such as '3 years' or '364 days'; say what in entity."),
}

GenericFieldName = Literal[
    "document_date",
    "effective_date",
    "deadline",
    "monetary_amount",
    "percentage",
    "party",
    "person",
    "location",
    "duration",
]

ALL_FIELDS = FIELDS | GENERIC_FIELDS


class GenericFactOut(FactOut):
    field: GenericFieldName  # type: ignore[assignment]


class GenericExtractionOut(BaseModel):
    facts: list[GenericFactOut]


@dataclass(frozen=True)
class Profile:
    name: str
    # Stored as `schema_version`, so it is part of the idempotency key.
    version: str
    subject: str
    fields: dict[str, tuple[Kind, str]]
    fact_model: type[FactOut]
    output_model: type[BaseModel]


SEC_8K = Profile("sec-8k", SCHEMA_VERSION, "SEC Form 8-K filings", FIELDS, FactOut, ExtractionOut)
GENERIC = Profile(
    "generic",
    "g1",
    "business documents such as contracts, reports, letters and policies",
    GENERIC_FIELDS,
    GenericFactOut,
    GenericExtractionOut,
)
UPLOAD_DOC_TYPE = "upload"


def profile_for(doc_type: str) -> Profile:
    return GENERIC if doc_type == UPLOAD_DOC_TYPE else SEC_8K
