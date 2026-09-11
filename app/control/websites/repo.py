from sqlalchemy import select
from sqlalchemy.orm import Session

from app.control.websites.models import Website


def get_all_websites(db: Session) -> list[Website]:
    return list(db.scalars(select(Website).order_by(Website.name, Website.id)).all())


def get_website(db: Session, website_id: int) -> Website | None:
    return db.get(Website, website_id)
