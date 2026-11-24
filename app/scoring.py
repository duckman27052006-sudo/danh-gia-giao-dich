from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Integer, func, select, text
from sqlalchemy.orm import Session

from app.features import build_context
from app.merchants import get_or_create_merchant
from app.ml.service import contributions, metadata, predict_probability
from app.models import Case, CaseEvent, Setting, Transaction, utcnow
from app.rules import evaluate_rules, load_enabled_rules
from app.schemas import TransactionIn
from app.timeutils import to_naive_utc

SLA_HOURS = {"P1": 4, "P2": 12, "P3": 48}

__all__ = ["SLA_HOURS", "ingest_transaction", "to_naive_utc"]


def get_settings_row(db: Session) -> Setting:
    row = db.get(Setting, 1)
    if row is None:
        row = Setting(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def next_case_code(db: Session) -> str:
    year = utcnow().year
    prefix = f"CASE-{year}-"
    # Khoá advisory theo transaction để hai request đồng thời không sinh trùng code.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('fraudlens:case-code'))"))
    latest_sequence = db.scalar(
        select(func.max(func.split_part(Case.code, "-", 3).cast(Integer))).where(
            Case.code.op("~")(f"^{prefix}[0-9]+$")
        )
    )
    sequence = (latest_sequence or 0) + 1
    return f"{prefix}{sequence:04d}"


def build_runtime_context(db: Session, payload: TransactionIn, occurred_at: datetime) -> dict[str, Any]:
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.customer_id == payload.customer_id, Transaction.occurred_at < occurred_at)
        .order_by(Transaction.occurred_at.desc())
        .limit(400)
    ).all()
    history = [
        {
            "amount": float(row.amount),
            "occurred_at": row.occurred_at,
            "device_id": row.device_id,
            "merchant_name": row.merchant_name,
            "merchant_category": row.merchant_category,
            "ip_country": row.ip_country,
        }
        for row in rows
    ]
    ctx = build_context(
        amount=payload.amount,
        occurred_at=occurred_at,
        card_country=payload.card_country.upper(),
        ip_country=payload.ip_country.upper(),
        device_id=payload.device_id,
        merchant_category=payload.merchant_category,
        channel=payload.channel,
        history=history,
        now=occurred_at,
    )
    first_seen = db.scalar(
        select(func.min(Transaction.occurred_at)).where(Transaction.customer_id == payload.customer_id)
    )
    if first_seen is not None:
        ctx["account_age_days"] = max((occurred_at - first_seen).days, 0)
    else:
        ctx["account_age_days"] = 0
    ctx["merchant_country"] = payload.merchant_country.upper()
    ctx["amount"] = payload.amount
    return ctx


def combine_scores(
    probability: float, rule_score: float, settings_row: Setting
) -> tuple[float, str, bool, list[str]]:
    """Gộp xác suất ML và điểm rule thành điểm cuối + band + trạng thái gắn cờ.

    Đây là **nguồn duy nhất** cho công thức chấm điểm, dùng chung cho runtime
    (``score_context``) và cho seed dữ liệu demo (``app/seed.py``) — trước đây
    seed tự cài lại công thức nên hai đường chấm điểm có thể lệch nhau.

    Trước đây điểm cuối chỉ là blend tuyến tính ``ml×w_ml + rule×w_rule``. Với
    trọng số mặc định 0.55/0.45 và ngưỡng cảnh báo 55, **không tín hiệu nào một
    mình có thể gây gắn cờ**: ML tối đa 55 điểm, rule tối đa 45. Hệ quả đo được
    trên tập test: recall chỉ 0.473 dù model đạt precision 0.987 — rất nhiều
    giao dịch rủi ro cao nhưng không có rule hit bị bỏ qua.

    Cách sửa: giữ blend làm điểm nền, nhưng cho mỗi tín hiệu một "cổng" riêng.
    Khi một tín hiệu vượt cổng của chính nó, điểm cuối không được thấp hơn tín
    hiệu đó — nhờ vậy blend không pha loãng tín hiệu mạnh, còn thứ tự ưu tiên
    và risk band vẫn nhất quán với một ngưỡng cảnh báo duy nhất.
    """
    ml_score = round(probability * 100, 1)
    ml_weight = max(settings_row.ml_weight, 0.0)
    rule_weight = max(settings_row.rule_weight, 0.0)
    total_weight = ml_weight + rule_weight or 1.0
    blended = (ml_score * (ml_weight / total_weight)) + (rule_score * (rule_weight / total_weight))

    ml_gate_hit = probability >= settings_row.ml_flag_probability
    rule_gate_hit = rule_score >= settings_row.rule_flag_threshold
    risk_score = max(blended, ml_score if ml_gate_hit else 0.0, rule_score if rule_gate_hit else 0.0)
    risk_score = round(max(0.0, min(risk_score, 100.0)), 1)

    if risk_score >= settings_row.high_threshold:
        band = "critical"
    elif risk_score >= settings_row.review_threshold:
        band = "high"
    elif risk_score >= settings_row.review_threshold * 0.65:
        band = "medium"
    else:
        band = "low"

    reasons = ["blend"]
    if ml_gate_hit:
        reasons.append("ml")
    if rule_gate_hit:
        reasons.append("rule")

    return risk_score, band, risk_score >= settings_row.review_threshold, reasons


def score_context(
    db: Session, ctx: dict[str, Any], settings_row: Setting
) -> tuple[float, list[dict[str, Any]], float, float, list[dict[str, Any]], str, bool, list[str]]:
    """Chấm điểm một context ở đường ingest runtime (xem ``combine_scores``)."""

    probability = predict_probability(ctx)
    ml_score = round(probability * 100, 1)
    rules = load_enabled_rules(db)
    rule_score, hits = evaluate_rules(rules, ctx)

    risk_score, band, is_flagged, reasons = combine_scores(probability, rule_score, settings_row)
    signals = contributions(ctx, risk_score)

    for rule in rules:
        if any(hit["rule_id"] == rule.id for hit in hits):
            rule.hit_count += 1
            rule.last_hit_at = utcnow()

    return ml_score, hits, rule_score, risk_score, signals, band, is_flagged, reasons


def priority_for(risk_score: float, amount: float, settings_row: Setting) -> str:
    """Ưu tiên suy ra từ chính ngưỡng cấu hình, không dùng số hard-code."""
    if risk_score >= settings_row.high_threshold or amount >= 40_000_000:
        return "P1"
    if risk_score >= settings_row.review_threshold or amount >= 10_000_000:
        return "P2"
    return "P3"


def create_case_for(
    db: Session,
    txn: Transaction,
    settings_row: Setting,
    reasons: list[str] | None = None,
) -> Case:
    priority = priority_for(txn.risk_score, float(txn.amount), settings_row)
    now = utcnow()
    case = Case(
        code=next_case_code(db),
        transaction_id=txn.id,
        priority=priority,
        status="open",
        risk_score=txn.risk_score,
        sla_due_at=now + timedelta(hours=SLA_HOURS[priority]),
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()
    reasons = reasons or []
    trigger = {
        "ml": "mô hình ML vượt ngưỡng riêng",
        "rule": "rule engine vượt ngưỡng riêng",
    }
    extra = [trigger[key] for key in ("ml", "rule") if key in reasons]
    suffix = f" — gắn cờ bởi {', '.join(extra)}" if extra else ""
    db.add(
        CaseEvent(
            case_id=case.id,
            type="created",
            message=(
                f"Hệ thống gắn cờ giao dịch với điểm rủi ro {txn.risk_score:.0f}/100 "
                f"({len(txn.rule_hits)} rule khớp){suffix}. Chờ analyst xác minh."
            ),
            meta={
                "risk_score": txn.risk_score,
                "ml_score": txn.ml_score,
                "rule_score": txn.rule_score,
                "priority": priority,
                "flag_reasons": reasons,
            },
        )
    )
    return case


def ingest_transaction(
    db: Session,
    payload: TransactionIn,
    *,
    simulated: bool = False,
    commit: bool = True,
) -> Transaction:
    occurred_at = to_naive_utc(payload.occurred_at) if payload.occurred_at else utcnow()
    settings_row = get_settings_row(db)
    merchant = get_or_create_merchant(
        db,
        payload.merchant_name,
        payload.merchant_category,
        payload.merchant_country,
    )

    ctx = build_runtime_context(db, payload, occurred_at)
    ml_score, hits, rule_score, risk_score, signals, band, is_flagged, reasons = score_context(
        db, ctx, settings_row
    )

    txn = Transaction(
        external_id=payload.external_id or f"TXN-{uuid.uuid4().hex[:12].upper()}",
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        amount=payload.amount,
        currency=payload.currency.upper(),
        channel=payload.channel,
        merchant_id=merchant.id,
        merchant_name=payload.merchant_name,
        merchant_category=payload.merchant_category,
        merchant_country=payload.merchant_country.upper(),
        card_country=payload.card_country.upper(),
        ip_country=payload.ip_country.upper(),
        device_id=payload.device_id,
        occurred_at=occurred_at,
        ingested_at=utcnow(),
        hour=int(ctx["hour"]),
        is_night=bool(ctx["is_night"]),
        country_mismatch=bool(ctx["country_mismatch"]),
        new_device=bool(ctx["new_device"]),
        velocity_1h=int(ctx["velocity_1h"]),
        velocity_24h=int(ctx["velocity_24h"]),
        amount_ratio=float(ctx["amount_ratio"]),
        distinct_merchants_24d=int(ctx["distinct_merchants_24d"]),
        account_age_days=int(ctx["account_age_days"]),
        ml_score=ml_score,
        rule_score=rule_score,
        risk_score=risk_score,
        risk_band=band,
        is_flagged=is_flagged,
        rule_hits=hits,
        contributions=signals,
        model_version=str(metadata()["version"]),
        is_simulated=simulated,
    )
    db.add(txn)
    db.flush()

    if is_flagged:
        create_case_for(db, txn, settings_row, reasons)

    if commit:
        db.commit()
        db.refresh(txn)
    return txn
