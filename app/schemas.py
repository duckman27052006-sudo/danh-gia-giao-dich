from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer


def _serialize_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


UTCDateTime = Annotated[datetime, PlainSerializer(_serialize_utc, return_type=str, when_used="json")]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth & users ----------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLite(ORMModel):
    id: str
    full_name: str
    email: str
    role: str


class UserOut(UserLite):
    is_active: bool
    created_at: UTCDateTime
    last_login_at: UTCDateTime | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(admin|analyst|viewer)$")


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: str | None = Field(default=None, pattern="^(admin|analyst|viewer)$")
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------- Transactions ----------


class TransactionIn(BaseModel):
    external_id: str | None = None
    customer_id: str = Field(min_length=2, max_length=40)
    customer_name: str = "Khách hàng"
    amount: float = Field(gt=0)
    currency: str = "VND"
    channel: str = Field(default="online", pattern="^(online|pos|atm|transfer)$")
    merchant_name: str
    merchant_category: str
    merchant_country: str = "VN"
    card_country: str = "VN"
    ip_country: str = "VN"
    device_id: str = "unknown-device"
    occurred_at: UTCDateTime | None = None


class CaseBrief(ORMModel):
    id: str
    code: str
    status: str
    priority: str
    decision: str | None = None


class TransactionOut(ORMModel):
    id: str
    external_id: str
    customer_id: str
    customer_name: str
    amount: float
    currency: str
    channel: str
    merchant_name: str
    merchant_category: str
    merchant_country: str
    card_country: str
    ip_country: str
    device_id: str
    occurred_at: UTCDateTime
    ingested_at: UTCDateTime
    hour: int
    is_night: bool
    country_mismatch: bool
    new_device: bool
    velocity_1h: int
    velocity_24h: int
    amount_ratio: float
    distinct_merchants_24d: int
    account_age_days: int
    ml_score: float
    rule_score: float
    risk_score: float
    risk_band: str
    is_flagged: bool
    rule_hits: list
    contributions: list
    model_version: str
    is_simulated: bool
    case: CaseBrief | None = None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
    pages: int


class SimulateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=25)
    fraud_bias: float = Field(default=0.3, ge=0, le=1)


# ---------- Cases ----------


class NoteOut(ORMModel):
    id: str
    body: str
    kind: str
    created_at: UTCDateTime
    author: UserLite | None = None


class EventOut(ORMModel):
    id: str
    type: str
    message: str
    meta: dict
    created_at: UTCDateTime
    actor: UserLite | None = None


class ExplanationOut(ORMModel):
    id: str
    provider: str
    model: str
    content: dict
    signals: list
    latency_ms: int
    created_at: UTCDateTime


class CaseListItem(ORMModel):
    id: str
    code: str
    priority: str
    status: str
    decision: str | None
    risk_score: float
    created_at: UTCDateTime
    updated_at: UTCDateTime
    sla_due_at: UTCDateTime | None
    assignee: UserLite | None = None
    transaction: TransactionOut


class CasePage(BaseModel):
    items: list[CaseListItem]
    total: int
    page: int
    page_size: int
    pages: int


class CaseDetail(ORMModel):
    id: str
    code: str
    priority: str
    status: str
    decision: str | None
    decision_note: str | None
    risk_score: float
    created_at: UTCDateTime
    updated_at: UTCDateTime
    resolved_at: UTCDateTime | None
    sla_due_at: UTCDateTime | None
    assignee: UserLite | None
    transaction: TransactionOut
    notes: list[NoteOut]
    events: list[EventOut]
    explanations: list[ExplanationOut]
    latest_explanation: ExplanationOut | None = None


class CaseUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_review|awaiting_info|resolved)$")
    assigned_to: str | None = None
    priority: str | None = Field(default=None, pattern="^(P1|P2|P3)$")


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(confirmed_fraud|false_positive|escalated)$")
    note: str = Field(min_length=10, max_length=4000)
    confirm: bool
    close_case: bool = True


class NoteCreate(BaseModel):
    body: str = Field(min_length=2, max_length=4000)
    kind: str = Field(default="note", pattern="^(note|ai_draft)$")


# ---------- Rules ----------


class RuleCondition(BaseModel):
    field: str
    op: str = Field(pattern="^(>|>=|<|<=|==|!=|in|not_in)$")
    value: float | int | str | list[str]


class RuleBase(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = ""
    conditions: list[RuleCondition] = Field(min_length=1)
    weight: int = Field(ge=1, le=100)
    severity: str = Field(default="medium", pattern="^(low|medium|high)$")
    category: str = Field(default="general", max_length=30)
    enabled: bool = True


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = None
    # min_length=1 để PATCH {"conditions": []} trả 422 thay vì đâm CHECK constraint
    # ck_rules_conditions_array ở tầng DB (lỗi 500 và mất audit của thao tác).
    conditions: list[RuleCondition] | None = Field(default=None, min_length=1)
    weight: int | None = Field(default=None, ge=1, le=100)
    severity: str | None = Field(default=None, pattern="^(low|medium|high)$")
    category: str | None = Field(default=None, max_length=30)
    enabled: bool | None = None


class RuleOut(ORMModel):
    id: str
    name: str
    description: str
    conditions: list
    weight: int
    severity: str
    category: str
    enabled: bool
    hit_count: int
    last_hit_at: UTCDateTime | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class RuleTestRequest(BaseModel):
    transaction_id: str


# ---------- Dashboard ----------


class DashboardSummary(BaseModel):
    total_transactions: int
    flagged_transactions: int
    total_volume: float
    fraud_rate: float
    open_cases: int
    p1_cases: int
    unassigned_cases: int
    confirmed_fraud: int
    false_positive: int
    precision: float
    amount_at_risk: float
    prevented_amount: float
    avg_resolution_hours: float
    today_transactions: int
    today_flagged: int
    delta_volume_pct: float
    model_version: str
    model_auc: float
    ai_provider: str


class TrendPoint(BaseModel):
    date: str
    total: int
    flagged: int
    confirmed: int
    volume: float


class BreakdownPoint(BaseModel):
    name: str
    value: float
    extra: float | None = None


class DashboardData(BaseModel):
    summary: DashboardSummary
    trend: list[TrendPoint]
    channels: list[BreakdownPoint]
    categories: list[BreakdownPoint]
    score_bands: list[BreakdownPoint]
    priority_queue: list[BreakdownPoint]
    recent_alerts: list[CaseListItem]
    rules_performance: list[dict]


class AuditLogOut(ORMModel):
    id: str
    actor_email: str
    action: str
    entity_type: str
    entity_id: str
    before: dict | None
    after: dict | None
    ip: str
    created_at: UTCDateTime


class AuditPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
    pages: int


# ---------- Settings ----------


class SettingsOut(ORMModel):
    review_threshold: float
    high_threshold: float
    ml_weight: float
    rule_weight: float
    ml_flag_probability: float
    rule_flag_threshold: float
    ai_enabled: bool
    updated_at: UTCDateTime


class SettingsUpdate(BaseModel):
    review_threshold: float = Field(ge=10, le=95)
    high_threshold: float = Field(ge=20, le=100)
    ml_weight: float = Field(ge=0, le=1)
    rule_weight: float = Field(ge=0, le=1)
    # Ngưỡng thành phần: xác suất ML tối thiểu để model tự gắn cờ, và tổng điểm
    # rule tối thiểu để rule engine tự gắn cờ khi model cho điểm thấp.
    ml_flag_probability: float = Field(default=0.65, ge=0.05, le=1)
    rule_flag_threshold: float = Field(default=80, ge=20, le=100)
    ai_enabled: bool


class ModelInfo(BaseModel):
    version: str
    trained_at: str
    algorithm: str
    auc: float
    precision: float
    recall: float
    samples: int
    feature_importance: list[dict]
    baseline: dict
