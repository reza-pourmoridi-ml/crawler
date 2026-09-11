from sqlalchemy.orm import Session

from app.infra.db import SessionLocal


def get_seed_session() -> Session:
    return SessionLocal()