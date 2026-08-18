"""Pure analysis engines.

Nothing in this package imports SQLAlchemy or FastAPI. Functions take plain
numbers and dataclasses and return :mod:`app.schemas.analysis` result objects,
which makes every rule in here unit-testable without a database, a fixture or an
HTTP client - see ``tests/unit``.
"""
