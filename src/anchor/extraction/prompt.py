"""The extraction prompt. Any edit that can change model output bumps `PROMPT_VERSION`."""

from anchor.extraction.schema import FIELDS

PROMPT_VERSION = "p1"

_FIELD_LIST = "\n".join(f"- {name} ({kind.value}): {desc}" for name, (kind, desc) in FIELDS.items())

SYSTEM = f"""You extract structured facts from SEC Form 8-K filings.

Return JSON with a single key "facts": a list of objects with keys
"field", "value", "quote", "entity", "confidence".

Fields you may report:
{_FIELD_LIST}

Rules:
- "value" must be copied character for character from the document. Do not reformat,
  round, convert units or translate it.
- "quote" must be a verbatim passage of the document, one sentence or table row at
  most, that contains "value". Do not paraphrase, shorten with ellipses or join
  separate passages.
- Report a field only when the document states it. Never infer or calculate a value.
  If the numbers are only in an attached exhibit that is not part of this text,
  do not report them.
- A field may appear several times (several Items, several officers). Use "entity"
  to say who or what each value belongs to; otherwise set it to null.
- "confidence" is your probability, from 0 to 1, that the value is correct for the field.
- If nothing applies, return {{"facts": []}}."""


def build_user_prompt(text: str) -> str:
    return f"<document>\n{text}\n</document>"
