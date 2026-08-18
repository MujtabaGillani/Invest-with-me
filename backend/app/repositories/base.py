"""Repository base class.

Repositories own SQL. Services own business rules. The split exists so that a
rule can be unit-tested against a fake repository, and so that a query can be
optimised without reading the logic that depends on it.

Rules for this layer:

* No commits. Transaction boundaries belong to the service that owns the unit of
  work - see :mod:`app.db.session`.
* No business decisions. A repository may filter and order; it may not decide
  whether a plan is allowed to be committed.
* Return ORM entities or plain tuples, never API schemas.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    """Shared CRUD helpers for a single model."""

    #: Set by each subclass.
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: int) -> ModelT | None:
        """Fetch by primary key, or ``None``."""
        return self.session.get(self.model, entity_id)

    def add(self, entity: ModelT) -> ModelT:
        """Stage an insert.

        ``flush`` (not ``commit``) so the caller gets the generated primary key
        while the surrounding transaction stays open and abortable.
        """
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        """Stage a delete."""
        self.session.delete(entity)
        self.session.flush()

    def count(self) -> int:
        """Total rows for this model."""
        return self.session.scalar(select(func.count()).select_from(self.model)) or 0

    def list_all(self, *, limit: int | None = None, offset: int = 0) -> Sequence[ModelT]:
        """Unfiltered listing, primarily for admin and test use."""
        statement = select(self.model).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.scalars(statement).all()
