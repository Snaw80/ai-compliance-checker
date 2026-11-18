"""Postgres connection helper."""

from __future__ import annotations

import os

import psycopg

DEFAULT_URL = "postgresql://aiact:aiact@localhost:5433/aiact"


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ.get("DATABASE_URL", DEFAULT_URL))


def to_pgvector(v: list[float]) -> str:
    """pgvector text literal; pass with a `::vector` cast (avoids the pgvector adapter dependency)."""
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"
