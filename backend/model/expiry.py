"""Durable daily expiry progress shared by scheduled and manual jobs."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DailyExpiryRun(Base):
    __tablename__ = 'daily_expiry_runs'

    scheduled_date: Mapped[date] = mapped_column(Date, primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    expired_items: Mapped[int] = mapped_column(BigInteger)
    closed_reports: Mapped[int] = mapped_column(BigInteger)
