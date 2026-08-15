from app.infra.db import Base # ایمپورت بیس صحیح
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

class Job(Base): # ارث‌بری از بیس صحیح
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="pending")
