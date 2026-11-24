from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import log_action
from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import Transaction, User
from app.schemas import SimulateRequest, TransactionIn, TransactionOut, TransactionPage
from app.scoring import ingest_transaction
from app.simulator import simulate_transactions
from app.timeutils import to_naive_utc

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionPage)
def list_transactions(
    q: str | None = None,
    risk_band: str | None = None,
    flagged: bool | None = None,
    channel: str | None = None,
    customer_id: str | None = None,
    min_score: float | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=5, le=100),
    sort: str = Query(default="recent", pattern="^(recent|score|amount)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionPage:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                Transaction.customer_name.ilike(pattern),
                Transaction.customer_id.ilike(pattern),
                Transaction.merchant_name.ilike(pattern),
                Transaction.external_id.ilike(pattern),
            )
        )
    if risk_band and risk_band != "all":
        conditions.append(Transaction.risk_band == risk_band)
    if flagged is not None:
        conditions.append(Transaction.is_flagged.is_(flagged))
    if channel and channel != "all":
        conditions.append(Transaction.channel == channel)
    if customer_id:
        conditions.append(Transaction.customer_id == customer_id)
    if min_score is not None:
        conditions.append(Transaction.risk_score >= min_score)
    if date_from is not None:
        conditions.append(Transaction.occurred_at >= to_naive_utc(date_from))
    if date_to is not None:
        conditions.append(Transaction.occurred_at <= to_naive_utc(date_to))

    total = db.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0
    order = {
        "recent": Transaction.occurred_at.desc(),
        "score": Transaction.risk_score.desc(),
        "amount": Transaction.amount.desc(),
    }[sort]
    items = db.scalars(
        select(Transaction)
        .where(*conditions)
        .order_by(order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = max((total + page_size - 1) // page_size, 1)
    return TransactionPage(
        items=[TransactionOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy giao dịch")
    return txn


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionIn,
    request: Request,
    actor: User = Depends(require_roles("admin", "analyst")),
    db: Session = Depends(get_db),
) -> Transaction:
    try:
        txn = ingest_transaction(db, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Mã giao dịch (external_id) đã tồn tại") from exc
    log_action(
        db,
        actor=actor,
        action="transaction.ingest",
        entity_type="transaction",
        entity_id=txn.id,
        after={
            "external_id": txn.external_id,
            "amount": float(txn.amount),
            "risk_score": txn.risk_score,
            "flagged": txn.is_flagged,
        },
        request=request,
    )
    db.commit()
    db.refresh(txn)
    return txn


@router.post("/simulate")
def simulate(
    payload: SimulateRequest,
    request: Request,
    actor: User = Depends(require_roles("admin", "analyst")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        items = simulate_transactions(db, count=payload.count, fraud_bias=payload.fraud_bias)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    flagged = sum(1 for item in items if item.is_flagged)
    log_action(
        db,
        actor=actor,
        action="transaction.simulate",
        entity_type="transaction",
        entity_id="batch",
        after={"count": len(items), "flagged": flagged, "fraud_bias": payload.fraud_bias},
        request=request,
    )
    db.commit()
    return {
        "created": len(items),
        "flagged": flagged,
        "items": [TransactionOut.model_validate(item) for item in items],
    }
