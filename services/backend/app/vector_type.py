"""Native pgvector in deployment, JSON only for SQLite development/tests."""
import json
from sqlalchemy import JSON
from sqlalchemy.types import UserDefinedType


class PGVector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        return 'public.vector'

    def bind_processor(self, dialect):
        return lambda value: json.dumps(value) if value is not None else None

    def result_processor(self, dialect, coltype):
        return lambda value: json.loads(value) if isinstance(value, str) else value


def vector_type():
    return JSON().with_variant(PGVector(), 'postgresql')
