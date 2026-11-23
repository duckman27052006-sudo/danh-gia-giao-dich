from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import require_roles
from app.explain import resolve_ai_provider
from app.ml.service import metadata
from app.models import Case, Rule, Transaction, User, utcnow
from app.schemas import (
    BreakdownPoint,
    CaseListItem,
    DashboardData,
    DashboardSummary,
    TrendPoint,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

AI_PROVIDER_LABELS = {
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
}


def _ai_provider_label() -> str:
    """Nhãn nhà cung cấp AI đang dùng, tính theo đúng thứ tự ưu tiên của
    ``resolve_ai_provider`` (OpenRouter → OpenAI → Anthropic) và công tắc chung."""
    provider = resolve_ai_provider()
    if provider is None or not settings.ai_enabled:
        return "Offline template"
    return AI_PROVIDER_LABELS.get(provider.name, provider.name)

BAND_LABELS = {"critical": "Rất cao", "high": "Cao", "medium": "Trung bình", "low": "Thấp"}


def _local_date_key(value) -> str:
    aware = value.replace(tzinfo=None) if value.tzinfo else value
    from datetime import timezone as _tz

    aware = aware.replace(tzinfo=_tz.utc) + timedelta(hours=7)
    return aware.strftime("%Y-%m-%d")


@router.get("", response_model=DashboardData)
def dashboard(
    days: int = Query(default=30, ge=7, le=180),
    _: User = Depends(require_roles("admin", "analyst", "viewer")),
    db: Session = Depends(get_db),
) -> DashboardData:
    now = utcnow()
    since = now - timedelta(days=days)
    today = now - timedelta(hours=24)

    total_transactions, total_volume = db.execute(
        select(
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.amount), 0),
        ).where(Transaction.occurred_at >= since)
    ).one()
    total_transactions, total_volume = int(total_transactions), float(total_volume)
    flagged_count = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.occurred_at >= since, Transaction.is_flagged.is_(True))
    ) or 0

    open_cases = db.scalar(
        select(func.count()).select_from(Case).where(Case.status != "resolved")
    ) or 0
    p1_cases = db.scalar(
        select(func.count()).select_from(Case).where(Case.status != "resolved", Case.priority == "P1")
    ) or 0
    unassigned = db.scalar(
        select(func.count()).select_from(Case).where(Case.status != "resolved", Case.assigned_to.is_(None))
    ) or 0
    confirmed = db.scalar(
        select(func.count()).select_from(Case).where(Case.decision == "confirmed_fraud")
    ) or 0
    false_positive = db.scalar(
        select(func.count()).select_from(Case).where(Case.decision == "false_positive")
    ) or 0
    precision = (confirmed / (confirmed + false_positive) * 100) if (confirmed + false_positive) else 0.0

    amount_at_risk = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .join(Case, Case.transaction_id == Transaction.id)
        .where(Case.status != "resolved")
    ) or 0
    prevented = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .join(Case, Case.transaction_id == Transaction.id)
        .where(Case.decision == "confirmed_fraud")
    ) or 0

    resolved_rows = db.execute(
        select(Case.created_at, Case.resolved_at).where(Case.resolved_at.is_not(None)).limit(500)
    ).all()
    durations = [
        (resolved_at - created_at).total_seconds() / 3600
        for created_at, resolved_at in resolved_rows
        if resolved_at and created_at
    ]
    avg_resolution = sum(durations) / len(durations) if durations else 0.0

    today_total = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.occurred_at >= today)
    ) or 0
    today_flagged = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.occurred_at >= today, Transaction.is_flagged.is_(True))
    ) or 0

    prev_start = now - timedelta(days=14)
    prev_end = now - timedelta(days=7)
    current_volume = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.occurred_at >= now - timedelta(days=7)
        )
    ) or 0
    previous_volume = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.occurred_at >= prev_start, Transaction.occurred_at < prev_end
        )
    ) or 0
    delta = ((float(current_volume) - float(previous_volume)) / float(previous_volume) * 100) if previous_volume else 0.0

    rows = db.execute(
        select(
            Transaction.occurred_at,
            Transaction.is_flagged,
            Transaction.amount,
            Transaction.risk_band,
            Transaction.channel,
            Transaction.merchant_category,
        ).where(Transaction.occurred_at >= since)
    ).all()

    trend_map: dict[str, dict] = defaultdict(lambda: {"total": 0, "flagged": 0, "confirmed": 0, "volume": 0.0})
    channel_map: dict[str, dict] = defaultdict(lambda: {"total": 0, "flagged": 0})
    category_map: dict[str, dict] = defaultdict(lambda: {"total": 0, "flagged": 0})
    band_map: dict[str, int] = defaultdict(int)

    for occurred_at, is_flagged, amount, band, channel, category in rows:
        key = _local_date_key(occurred_at)
        bucket = trend_map[key]
        bucket["total"] += 1
        bucket["volume"] += float(amount)
        if is_flagged:
            bucket["flagged"] += 1
        channel_map[channel]["total"] += 1
        if is_flagged:
            channel_map[channel]["flagged"] += 1
        category_map[category]["total"] += 1
        if is_flagged:
            category_map[category]["flagged"] += 1
        band_map[band] += 1

    confirmed_by_date = db.execute(
        select(Case.resolved_at).where(Case.decision == "confirmed_fraud", Case.resolved_at >= since)
    ).all()
    for (resolved_at,) in confirmed_by_date:
        if resolved_at:
            trend_map[_local_date_key(resolved_at)]["confirmed"] += 1

    day_keys = []
    for offset in range(days - 1, -1, -1):
        key = _local_date_key(now - timedelta(days=offset))
        day_keys.append(key)

    trend = [
        TrendPoint(
            date=key,
            total=trend_map[key]["total"],
            flagged=trend_map[key]["flagged"],
            confirmed=trend_map[key]["confirmed"],
            volume=round(trend_map[key]["volume"], 2),
        )
        for key in day_keys
    ]
    channels = [
        BreakdownPoint(name=name, value=data["total"], extra=data["flagged"])
        for name, data in sorted(channel_map.items(), key=lambda item: item[1]["total"], reverse=True)
    ]
    categories = [
        BreakdownPoint(name=name, value=data["total"], extra=data["flagged"])
        for name, data in sorted(category_map.items(), key=lambda item: item[1]["flagged"], reverse=True)
    ][:8]
    score_bands = [
        BreakdownPoint(name=BAND_LABELS.get(band, band), value=count)
        for band, count in sorted(band_map.items(), key=lambda item: item[0], reverse=True)
    ]

    priority_rows = db.execute(
        select(Case.priority, func.count())
        .where(Case.status != "resolved")
        .group_by(Case.priority)
    ).all()
    priority_counts = {priority: count for priority, count in priority_rows}
    priority_queue = [
        BreakdownPoint(name=priority, value=priority_counts.get(priority, 0))
        for priority in ("P1", "P2", "P3")
    ]

    recent = db.scalars(
        select(Case)
        .where(Case.status != "resolved")
        .order_by(Case.risk_score.desc(), Case.created_at.desc())
        .limit(6)
    ).all()

    rules = db.scalars(select(Rule).order_by(Rule.hit_count.desc()).limit(6)).all()
    rules_performance = [
        {
            "id": rule.id,
            "name": rule.name,
            "hits": rule.hit_count,
            "weight": rule.weight,
            "severity": rule.severity,
            "enabled": rule.enabled,
        }
        for rule in rules
    ]

    model_meta = metadata()
    ai_provider = _ai_provider_label()

    summary = DashboardSummary(
        total_transactions=total_transactions,
        flagged_transactions=flagged_count,
        total_volume=total_volume,
        fraud_rate=round(flagged_count / total_transactions * 100, 2) if total_transactions else 0.0,
        open_cases=open_cases,
        p1_cases=p1_cases,
        unassigned_cases=unassigned,
        confirmed_fraud=confirmed,
        false_positive=false_positive,
        precision=round(precision, 1),
        amount_at_risk=float(amount_at_risk),
        prevented_amount=float(prevented),
        avg_resolution_hours=round(avg_resolution, 1),
        today_transactions=int(today_total),
        today_flagged=int(today_flagged),
        delta_volume_pct=round(delta, 1),
        model_version=model_meta["version"],
        model_auc=model_meta["auc"],
        ai_provider=ai_provider,
    )

    return DashboardData(
        summary=summary,
        trend=trend,
        channels=channels,
        categories=categories,
        score_bands=score_bands,
        priority_queue=priority_queue,
        recent_alerts=[CaseListItem.model_validate(case) for case in recent],
        rules_performance=rules_performance,
    )
