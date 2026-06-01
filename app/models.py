from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.clock import utc_now
from app.schemas import (
    DEFAULT_TIMEZONE,
    PRESET_FALLBACK_INTERVALS,
    SUBSCRIPTION_STATUS_PENDING,
    SYNC_STATUS_NEVER,
    WATCH_STATUS_PENDING,
)


class Base(DeclarativeBase):
    pass


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    app_token: Mapped[str] = mapped_column(Text)
    fallback_interval_minutes: Mapped[int] = mapped_column(Integer, default=PRESET_FALLBACK_INTERVALS[0])
    next_fallback_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    watch_status: Mapped[str] = mapped_column(Text, default=WATCH_STATUS_PENDING)
    subscription_status: Mapped[str] = mapped_column(Text, default=SUBSCRIPTION_STATUS_PENDING)
    sync_status: Mapped[str] = mapped_column(Text, default=SYNC_STATUS_NEVER)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_event_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    watch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscription_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_record_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    tables: Mapped[list[BitableTable]] = relationship(back_populates="monitor")
    current_records: Mapped[list[CurrentRecord]] = relationship(back_populates="monitor")
    event_logs: Mapped[list[EventLog]] = relationship(back_populates="monitor")
    sync_runs: Mapped[list[SyncRun]] = relationship(back_populates="monitor")
    worker_jobs: Mapped[list[WorkerJob]] = relationship(back_populates="monitor")


class BitableTable(Base):
    __tablename__ = "bitable_tables"
    __table_args__ = (UniqueConstraint("monitor_id", "table_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    table_id: Mapped[str] = mapped_column(Text)
    table_name: Mapped[str] = mapped_column(Text)
    field_schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    monitor: Mapped[Monitor] = relationship(back_populates="tables")


class CurrentRecord(Base):
    __tablename__ = "current_records"
    __table_args__ = (
        UniqueConstraint("monitor_id", "table_id", "record_id"),
        ForeignKeyConstraint(
            ("monitor_id", "table_id"),
            ("bitable_tables.monitor_id", "bitable_tables.table_id"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    table_id: Mapped[str] = mapped_column(Text)
    record_id: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    monitor: Mapped[Monitor] = relationship(back_populates="current_records")


class EventLog(Base):
    __tablename__ = "event_logs"
    __table_args__ = (UniqueConstraint("event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(Text)
    monitor_id: Mapped[int | None] = mapped_column(ForeignKey("monitors.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(Text)
    table_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    process_status: Mapped[str] = mapped_column(Text, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    monitor: Mapped[Monitor | None] = relationship(back_populates="event_logs")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    trigger_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stats_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    monitor: Mapped[Monitor] = relationship(back_populates="sync_runs")


class WorkerJob(Base):
    __tablename__ = "worker_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(Text)
    monitor_id: Mapped[int | None] = mapped_column(ForeignKey("monitors.id"), nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="queued")
    run_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    monitor: Mapped[Monitor | None] = relationship(back_populates="worker_jobs")


class TableJobLease(Base):
    __tablename__ = "table_job_leases"
    __table_args__ = (UniqueConstraint("monitor_id", "table_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    table_id: Mapped[str] = mapped_column(Text)
    worker_id: Mapped[str] = mapped_column(Text)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
