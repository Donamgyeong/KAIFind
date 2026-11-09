"""Durable daily backup execution history."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DatabaseBackup(Base):
    __tablename__ = 'database_backups'

    scheduled_date: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    object_key: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    expiry_run_id: Mapped[UUID | None] = mapped_column(Uuid)
