from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'analyst', 'viewer')", name="ck_users_role"),
        # Email được so sánh không phân biệt hoa/thường khi đăng nhập.
        Index("ux_users_email_lower", text("lower(email)"), unique=True),
    )


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    category: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(2), default="VN")
    risk_tier: Mapped[str] = mapped_column(String(10), default="low")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint("risk_tier IN ('low', 'medium', 'high')", name="ck_merchants_risk_tier"),
        CheckConstraint("char_length(country) = 2", name="ck_merchants_country"),
        Index("ux_merchants_name_lower", text("lower(name)"), unique=True),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    external_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(40))
    customer_name: Mapped[str] = mapped_column(String(120), default="Khách hàng")
    amount: Mapped[float] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    channel: Mapped[str] = mapped_column(String(20), default="online")
    # merchant_id là khoá chuẩn; các cột merchant_* bên dưới giữ snapshot tại
    # thời điểm giao dịch để audit không bị thay đổi khi merchant đổi thông tin.
    merchant_id: Mapped[str | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="SET NULL", name="fk_transactions_merchant"),
        nullable=True,
        index=True,
    )
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
    risk_band: Mapped[str] = mapped_column(String(10), default="low")
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_hits: Mapped[list] = mapped_column(JSONB, default=list)
    contributions: Mapped[list] = mapped_column(JSONB, default=list)
    model_version: Mapped[str] = mapped_column(String(30), default="untrained")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)

    case: Mapped[Case | None] = relationship(back_populates="transaction", uselist=False)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        CheckConstraint(
            "channel IN ('online', 'pos', 'atm', 'transfer')", name="ck_transactions_channel"
        ),
        CheckConstraint(
            "risk_band IN ('low', 'medium', 'high', 'critical')", name="ck_transactions_risk_band"
        ),
        CheckConstraint(
            "ml_score >= 0 AND ml_score <= 100 "
            "AND rule_score >= 0 AND rule_score <= 100 "
            "AND risk_score >= 0 AND risk_score <= 100",
            name="ck_transactions_scores",
        ),
        CheckConstraint("hour >= 0 AND hour <= 23", name="ck_transactions_hour"),
        CheckConstraint(
            "velocity_1h >= 0 AND velocity_24h >= 0", name="ck_transactions_velocity"
        ),
        CheckConstraint("amount_ratio >= 0", name="ck_transactions_amount_ratio"),
        CheckConstraint(
            "distinct_merchants_24d >= 0", name="ck_transactions_distinct_merchants"
        ),
        CheckConstraint("account_age_days >= 0", name="ck_transactions_account_age"),
        CheckConstraint("jsonb_typeof(rule_hits) = 'array'", name="ck_transactions_rule_hits_array"),
        CheckConstraint(
            "jsonb_typeof(contributions) = 'array'", name="ck_transactions_contributions_array"
        ),
        # Truy vấn nóng: dựng lịch sử theo khách hàng và lọc theo band/channel + ngày.
        Index("ix_transactions_customer_occurred", "customer_id", "occurred_at"),
        Index("ix_transactions_risk_band_occurred", "risk_band", "occurred_at"),
        Index("ix_transactions_channel_occurred", "channel", "occurred_at"),
        Index(
            "ix_transactions_flagged_recent",
            "occurred_at",
            postgresql_where=text("is_flagged"),
        ),
    )


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE", name="fk_cases_transaction"), unique=True
    )
    priority: Mapped[str] = mapped_column(String(4), default="P3")
    status: Mapped[str] = mapped_column(String(20), default="open")
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_cases_assigned_to"),
        nullable=True,
        index=True,
    )
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

    __table_args__ = (
        CheckConstraint("priority IN ('P1', 'P2', 'P3')", name="ck_cases_priority"),
        CheckConstraint(
            "status IN ('open', 'in_review', 'awaiting_info', 'resolved')", name="ck_cases_status"
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('confirmed_fraud', 'false_positive', 'escalated')",
            name="ck_cases_decision",
        ),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_cases_risk_score"),
        CheckConstraint(
            "status <> 'resolved' OR (decision IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_cases_resolved_consistency",
        ),
        # Hàng chờ lọc theo trạng thái + SLA; bảng mở dùng partial index nhỏ hơn.
        Index("ix_cases_status_sla", "status", "sla_due_at"),
        Index("ix_cases_created_at", "created_at"),
        Index(
            "ix_cases_open_priority",
            "priority",
            postgresql_where=text("status <> 'resolved'"),
        ),
    )


class CaseNote(Base):
    __tablename__ = "case_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE", name="fk_case_notes_case")
    )
    author_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_case_notes_author"),
        nullable=True,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="note")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="notes")
    author: Mapped[User | None] = relationship()

    __table_args__ = (
        CheckConstraint("kind IN ('note', 'ai_draft', 'decision')", name="ck_case_notes_kind"),
        Index("ix_case_notes_case_created", "case_id", "created_at"),
    )


class CaseEvent(Base):
    __tablename__ = "case_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE", name="fk_case_events_case")
    )
    type: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_case_events_actor"),
        nullable=True,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()

    __table_args__ = (
        CheckConstraint("jsonb_typeof(meta) = 'object'", name="ck_case_events_meta_object"),
        Index("ix_case_events_case_created", "case_id", "created_at"),
    )


class Explanation(Base):
    __tablename__ = "explanations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE", name="fk_explanations_case")
    )
    provider: Mapped[str] = mapped_column(String(20), default="offline")
    model: Mapped[str] = mapped_column(String(60), default="template-v1")
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    signals: Mapped[list] = mapped_column(JSONB, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_explanations_created_by"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="explanations")

    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="ck_explanations_latency"),
        CheckConstraint("jsonb_typeof(content) = 'object'", name="ck_explanations_content_object"),
        CheckConstraint("jsonb_typeof(signals) = 'array'", name="ck_explanations_signals_array"),
        Index("ix_explanations_case_created", "case_id", "created_at"),
    )


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[list] = mapped_column(JSONB, default=list)
    weight: Mapped[int] = mapped_column(Integer, default=10)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    category: Mapped[str] = mapped_column(String(30), default="general")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("weight >= 1 AND weight <= 100", name="ck_rules_weight"),
        CheckConstraint("severity IN ('low', 'medium', 'high')", name="ck_rules_severity"),
        CheckConstraint("hit_count >= 0", name="ck_rules_hit_count"),
        CheckConstraint(
            "jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) > 0",
            name="ck_rules_conditions_array",
        ),
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_sessions_user"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # Không đặt FK cho actor_id: audit phải tồn tại độc lập với vòng đời user.
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="system")
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    __table_args__ = (
        # Bộ lọc audit luôn đi kèm một cột phân loại + sắp xếp theo thời gian.
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_entity_created", "entity_type", "created_at"),
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
    )


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    review_threshold: Mapped[float] = mapped_column(Float, default=55.0)
    high_threshold: Mapped[float] = mapped_column(Float, default=78.0)
    ml_weight: Mapped[float] = mapped_column(Float, default=0.55)
    rule_weight: Mapped[float] = mapped_column(Float, default=0.45)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_settings_singleton"),
        CheckConstraint(
            "review_threshold >= 0 AND review_threshold <= 100 "
            "AND high_threshold >= 0 AND high_threshold <= 100 "
            "AND high_threshold > review_threshold",
            name="ck_settings_thresholds",
        ),
        CheckConstraint(
            "ml_weight >= 0 AND ml_weight <= 1 "
            "AND rule_weight >= 0 AND rule_weight <= 1 "
            "AND (ml_weight + rule_weight) > 0",
            name="ck_settings_weights",
        ),
    )
