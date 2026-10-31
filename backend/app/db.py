"""Conexión a la base de datos.

DATABASE_URL vacío usa SQLite local (perfiles.db). En producción apunta a PostgreSQL,
por ejemplo la cadena de conexión de Neon.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _url():
    url = os.environ.get("DATABASE_URL", "sqlite:///./perfiles.db")
    # Neon, Render y Heroku entregan postgres://; SQLAlchemy con psycopg 3 espera esto:
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


URL = _url()
engine = create_engine(
    URL,
    connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
