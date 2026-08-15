# app/infra/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.infra.config import settings
from pathlib import Path
from alembic import command
from alembic.config import Config
import os

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    root_dir = Path(__file__).resolve().parents[2]   # crawler/
    alembic_ini = root_dir / "alembic.ini"

    if not alembic_ini.exists():
        raise FileNotFoundError(f"Alembic config not found: {alembic_ini}")

    config = Config(str(alembic_ini))
    command.upgrade(config, "head")

