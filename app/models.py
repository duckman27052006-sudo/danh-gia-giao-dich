from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """UTC naive — mọi thời điểm trong hệ thống đều lưu/so sánh ở dạng này."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UTCDateTime(TypeDecorator[datetime]):
    """Cột thời gian luôn là UTC naive khi đọc/ghi.

    PostgreSQL trả về datetime *có* timezone cho cột ``timestamptz`` trong khi
    toàn bộ logic của app so sánh với ``utcnow()`` (naive) — chênh lệch này gây
    ``TypeError: can't compare offset-naive and offset-aware datetimes``.
    Dùng ``timestamp without time zone`` + chuẩn hoá ở hai đầu để thống nhất.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    cases: Mapped[list[Case]] = relationship(back_populates="assignee", foreign_keys="Case.assigned_to")


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    category: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(2), default="VN")
    risk_tier: Mapped[str] = mapped_column(String(10), default="low")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    external_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(40), index=True)
    customer_name: Mapped[str] = mapped_column(String(120), default="Khách hàng")
    amount: Mapped[float] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    channel: Mapped[str] = mapped_column(String(20), default="online")
    merchant_name: Mapped[str] = mapped_column(String(160))
    merchant_category: Mapped[str] = mapped_column(String(60))
    merchant_country: Mapped[str] = mapped_column(String(2), default="VN")
    card_country: Mapped[str] = mapped_column(String(2), default="VN")
    ip_country: Mapped[str] = mapped_column(String(2), default="VN")
    device_id: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    hour: Mapped[int] = mapped_column(Integer, default=12)
    is_night: Mapped[bool] = mapped_column(Boolean, default=False)
    country_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    new_device: Mapped[bool] = mapped_column(Boolean, default=False)
    velocity_1h: Mapped[int] = mapped_column(Integer, default=1)
    velocity_24h: Mapped[int] = mapped_column(Integer, default=1)
    amount_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    distinct_merchants_24d: Mapped[int] = mapped_column(Integer, default=1)
    account_age_days: Mapped[int] = mapped_column(Integer, default=30)

    ml_score: Mapped[float] = mapped_column(Float, default=0.0)
    rule_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    risk_band: Mapped[str] = mapped_column(String(10), default="low", index=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    rule_hits: Mapped[list] = mapped_column(JSON, default=list)
    contributions: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(30), default="untrained")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)

    # Truy vấn nóng: dựng lịch sử theo khách hàng và đếm giao dịch bị gắn cờ theo ngày.
    __table_args__ = (
        Index("ix_transactions_customer_occurred", "customer_id", "occurred_at"),
        Index("ix_transactions_flagged_occurred", "is_flagged", "occurred_at"),
    )

    case: Mapped[Case | None] = relationship(back_populates="transaction", uselist=False)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), unique=True)
    priority: Mapped[str] = mapped_column(String(4), default="P3", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    sla_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    transaction: Mapped[Transaction] = relationship(back_populates="case")
    assignee: Mapped[User | None] = relationship(back_populates="cases", foreign_keys=[assigned_to])
    notes: Mapped[list[CaseNote]] = relationship(back_populates="case", cascade="all, delete-orphan")
    events: Mapped[list[CaseEvent]] = relationship(back_populates="case", cascade="all, delete-orphan")
    explanations: Mapped[list[Explanation]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )

    # Hàng chờ lọc theo trạng thái và sắp xếp/đếm SLA quá hạn.
    __table_args__ = (Index("ix_cases_status_sla", "status", "sla_due_at"),)


class CaseNote(Base):
    __tablename__ = "case_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="note")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="notes")
    author: Mapped[User | None] = relationship()


class CaseEvent(Base):
    __tablename__ = "case_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()


class Explanation(Base):
    __tablename__ = "explanations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="offline")
    model: Mapped[str] = mapped_column(String(60), default="template-v1")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="explanations")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    weight: Mapped[int] = mapped_column(Integer, default=10)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    category: Mapped[str] = mapped_column(String(30), default="general")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="system")
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    review_threshold: Mapped[float] = mapped_column(Float, default=55.0)
    high_threshold: Mapped[float] = mapped_column(Float, default=78.0)
    ml_weight: Mapped[float] = mapped_column(Float, default=0.55)
    rule_weight: Mapped[float] = mapped_column(Float, default=0.45)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
