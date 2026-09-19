import os
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger("app.db")


def _register_numpy_adapters() -> None:
    """Let psycopg2 serialize numpy scalar types (np.float64, np.int64...).

    Without this, any INSERT that passes a numpy scalar renders the literal
    ``np.float64(...)`` into the SQL and Postgres fails with a bogus
    ``schema "np" does not exist`` error. psycopg2's built-in ``Float``
    quoter calls ``repr()``, which for numpy scalars is the ``np.float64(...)``
    form, so here we register a quoter that converts each scalar to its native
    Python equivalent first (``.item()``) and lets psycopg2 format that.
    """
    try:
        import numpy as np
        import psycopg2.extensions
    except ImportError:
        return

    pg = psycopg2.extensions

    class _NumpyQuoter(pg.ISQLQuote):
        def __init__(self, value):
            self._native = value.item()

        def getquoted(self):
            return pg.adapt(self._native).getquoted()

        def getbinary(self, conn):
            return pg.adapt(self._native).getbinary(conn)

        def prepare(self, conn):
            pass

    scalar_types = [
        np.float16, np.float32, np.float64,
        np.int8, np.int16, np.int32, np.int64,
        np.uint8, np.uint16, np.uint32, np.uint64,
        np.bool_,
    ]
    for np_type in scalar_types:
        psycopg2.extensions.register_adapter(np_type, _NumpyQuoter)


connect_args = {}
pool_kwargs: dict = {"pool_pre_ping": True}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    _register_numpy_adapters()
    pool_kwargs.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    })

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
    **pool_kwargs,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
