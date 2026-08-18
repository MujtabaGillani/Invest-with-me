"""Schema base classes and shared response wrappers.

Conventions applied across every schema in this package:

* **snake_case field names, end to end.** The JSON body uses the same names as
  the Python and TypeScript models. Camel-casing at the boundary buys nothing
  and costs one more place for a rename to go half-finished.
* **Read models are frozen.** Response objects are built once and serialised;
  making them immutable removes any doubt about whether a handler mutated a
  value after a service validated it.
* **Write models forbid unknown fields.** A typo in a client payload is a 422,
  not a silently ignored field.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReadSchema(BaseModel):
    """Base for anything the API returns."""

    model_config = ConfigDict(
        from_attributes=True,  # allows ``Model.model_validate(orm_row)``
        frozen=True,
        extra="forbid",
    )


class WriteSchema(BaseModel):
    """Base for anything the API accepts."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class Page[T](ReadSchema):
    """Envelope for paginated collections.

    Always returning ``total`` alongside the page lets the UI render "showing
    20 of 137" without a second count request.
    """

    items: list[T]
    total: int = Field(description="Total number of matching rows, ignoring pagination.")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class PaginationParams(BaseModel):
    """Reusable ``limit``/``offset`` query parameters.

    The 200-row ceiling is a denial-of-service guard: without it a single
    ``?limit=1000000`` serialises the whole table.
    """

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MessageResponse(ReadSchema):
    """Simple acknowledgement for endpoints with nothing better to return."""

    message: str


class Disclaimer(ReadSchema):
    """Standing disclaimer attached to every analytical response.

    Kept in the payload rather than only in the UI so that the caveat travels
    with the data - if a screenshot, export or third-party client consumes this
    API, the caveat is part of what it consumed.
    """

    is_financial_advice: bool = Field(
        default=False,
        description="Always false. This API scores stated criteria; it does not advise.",
    )
    text: str = Field(
        default=(
            "Educational and general in nature. These figures score a company against "
            "a fixed checklist and do not predict price movements. Nothing here is "
            "financial advice, and no checklist guarantees profit or protects against "
            "loss. Consider a licensed financial advisor for your own situation."
        )
    )


#: Single shared instance - the text never varies per request.
STANDARD_DISCLAIMER = Disclaimer()
