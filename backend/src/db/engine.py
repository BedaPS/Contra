"""Database engine and session factory.

Connection string is read from DATABASE_URL environment variable.
Default: MSSQL via pyodbc (mssql+pyodbc://...).
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mssql+pymssql://sa:Admin%401234@localhost:1433/contra",
)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_db():
    """FastAPI dependency — yields a SQLAlchemy session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
