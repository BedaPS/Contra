"""SQLAlchemy ORM base and common column mixins."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all Contra ORM models (code-first)."""

    pass
