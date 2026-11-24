from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import AuditLog, User
from app.schemas import AuditPage
from app.timeutils import to_naive_utc

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPage)
def list_audit(
    q: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=100),
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> AuditPage:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                AuditLog.actor_email.ilike(pattern),
                AuditLog.action.ilike(pattern),
                AuditLog.entity_id.ilike(pattern),
            )
        )
    if action and action != "all":
        conditions.append(AuditLog.action == action)
    if entity_type and entity_type != "all":
        conditions.append(AuditLog.entity_type == entity_type)
    if date_from:
        conditions.append(AuditLog.created_at >= to_naive_utc(date_from))
    if date_to:
        conditions.append(AuditLog.created_at <= to_naive_utc(date_to))

    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    items = db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = max((total + page_size - 1) // page_size, 1)
    return AuditPage(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/actions")
def list_actions(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    actions = db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)).all()
    entities = db.scalars(select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)).all()
    return {"actions": list(actions), "entities": list(entities)}
