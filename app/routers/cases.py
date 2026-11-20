from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case as sql_case
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import log_action
from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_roles
from app.explain import generate_explanation
from app.models import Case, CaseEvent, CaseNote, Explanation, Transaction, User, utcnow
from app.schemas import (
    CaseDetail,
    CaseListItem,
    CasePage,
    CaseUpdate,
    DecisionRequest,
    ExplanationOut,
    NoteCreate,
    NoteOut,
)

router = APIRouter(prefix="/cases", tags=["cases"])

PRIORITY_ORDER = sql_case({"P1": 1, "P2": 2, "P3": 3}, value=Case.priority, else_=9)
STATUS_ORDER = sql_case({"open": 1, "in_review": 2, "awaiting_info": 3, "resolved": 4}, value=Case.status, else_=9)


def _event(db: Session, case: Case, type_: str, message: str, actor: User | None, meta: dict | None = None) -> None:
    db.add(
        CaseEvent(
            case_id=case.id,
            type=type_,
            message=message,
            actor_id=actor.id if actor else None,
            meta=meta or {},
        )
    )


@router.get("", response_model=CasePage)
def list_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = None,
    assignee: str | None = None,
    q: str | None = None,
    min_score: float | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=5, le=100),
    sort: str = Query(default="priority", pattern="^(priority|recent|score|sla)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CasePage:
    conditions = []
    if status_filter and status_filter != "all":
        values = [item for item in status_filter.split(",") if item]
        conditions.append(Case.status.in_(values))
    if priority and priority != "all":
        conditions.append(Case.priority == priority)
    if assignee == "unassigned":
        conditions.append(Case.assigned_to.is_(None))
    elif assignee and assignee != "all":
        conditions.append(Case.assigned_to == assignee)
    if min_score is not None:
        conditions.append(Case.risk_score >= min_score)
    query = select(Case).join(Transaction)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Case.code.ilike(pattern),
                Transaction.customer_name.ilike(pattern),
                Transaction.customer_id.ilike(pattern),
                Transaction.merchant_name.ilike(pattern),
                Transaction.external_id.ilike(pattern),
            )
        )
    if conditions:
        query = query.where(*conditions)

    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0
    order = {
        "priority": (STATUS_ORDER, PRIORITY_ORDER, Case.risk_score.desc(), Case.created_at.asc()),
        "recent": (Case.created_at.desc(),),
        "score": (Case.risk_score.desc(),),
        "sla": (Case.sla_due_at.asc(),),
    }[sort]
    items = db.scalars(query.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    pages = max((total + page_size - 1) // page_size, 1)
    return CasePage(
        items=[CaseListItem.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/stats")
def case_stats(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(select(Case.status, Case.priority, func.count()).group_by(Case.status, Case.priority)).all()
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for status_value, priority_value, count in rows:
        by_status[status_value] = by_status.get(status_value, 0) + count
        by_priority[priority_value] = by_priority.get(priority_value, 0) + count
    open_priority_rows = db.execute(
        select(Case.priority, func.count()).where(Case.status != "resolved").group_by(Case.priority)
    ).all()
    open_by_priority = {priority: count for priority, count in open_priority_rows}
    unassigned = db.scalar(
        select(func.count()).select_from(Case).where(Case.assigned_to.is_(None), Case.status != "resolved")
    ) or 0
    overdue = db.scalar(
        select(func.count())
        .select_from(Case)
        .where(Case.status != "resolved", Case.sla_due_at < utcnow())
    ) or 0
    return {
        "by_status": by_status,
        "by_priority": by_priority,
        "open_by_priority": open_by_priority,
        "unassigned": unassigned,
        "overdue": overdue,
        "total": sum(by_status.values()),
    }


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(
    case_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseDetail:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy case")
    detail = CaseDetail.model_validate(case)
    explanations = sorted(case.explanations, key=lambda item: item.created_at, reverse=True)
    if explanations:
        detail.latest_explanation = ExplanationOut.model_validate(explanations[0])
    return detail


@router.patch("/{case_id}", response_model=CaseDetail)
def update_case(
    case_id: str,
    payload: CaseUpdate,
    request: Request,
    actor: User = Depends(require_roles("admin", "analyst")),
    db: Session = Depends(get_db),
) -> CaseDetail:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy case")

    before = {
        "status": case.status,
        "assigned_to": case.assigned_to,
        "priority": case.priority,
    }
    fields_set = payload.model_fields_set
    if "assigned_to" in fields_set:
        if payload.assigned_to:
            assignee = db.get(User, payload.assigned_to)
            if assignee is None or not assignee.is_active or assignee.role not in {"admin", "analyst"}:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Người được giao không hợp lệ")
            case.assigned_to = assignee.id
            _event(db, case, "assigned", f"Giao case cho {assignee.full_name}", actor)
        else:
            case.assigned_to = None
            _event(db, case, "assigned", "Bỏ phân công case", actor)
    if payload.status is not None:
        if payload.status == "resolved" and case.decision is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Phải ghi nhận quyết định của analyst trước khi đóng case",
            )
        if payload.status != case.status:
            case.status = payload.status
            _event(
                db,
                case,
                "status",
                f"Chuyển trạng thái: {before['status']} → {payload.status}",
                actor,
                {"from": before["status"], "to": payload.status},
            )
            if payload.status == "resolved":
                case.resolved_at = utcnow()
            elif case.status == "resolved":
                # Reopen: xoá mốc hoàn tất cũ, quyết định vẫn được giữ làm lịch sử.
                case.resolved_at = None
    if payload.priority is not None and payload.priority != case.priority:
        case.priority = payload.priority
        _event(db, case, "priority", f"Đổi ưu tiên: {before['priority']} → {payload.priority}", actor)
    case.updated_at = utcnow()

    log_action(
        db,
        actor=actor,
        action="case.update",
        entity_type="case",
        entity_id=case.id,
        before=before,
        after={"status": case.status, "assigned_to": case.assigned_to, "priority": case.priority},
        request=request,
    )
    db.commit()
    db.refresh(case)
    detail = CaseDetail.model_validate(case)
    explanations = sorted(case.explanations, key=lambda item: item.created_at, reverse=True)
    if explanations:
        detail.latest_explanation = ExplanationOut.model_validate(explanations[0])
    return detail


@router.post("/{case_id}/decision", response_model=CaseDetail)
def decide_case(
    case_id: str,
    payload: DecisionRequest,
    request: Request,
    actor: User = Depends(require_roles("admin", "analyst")),
    db: Session = Depends(get_db),
) -> CaseDetail:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy case")
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cần xác nhận rõ ràng trước khi ghi nhận kết luận")
    if case.decision is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Case đã có kết luận, không thể ghi đè")

    decision_labels = {
        "confirmed_fraud": "Xác nhận gian lận",
        "false_positive": "Cảnh báo sai (false positive)",
        "escalated": "Chuyển cấp xử lý",
    }
    label = decision_labels[payload.decision]

    case.decision = payload.decision
    case.decision_note = payload.note.strip()
    case.status = "resolved" if payload.close_case else "in_review"
    case.resolved_at = utcnow() if payload.close_case else None
    case.updated_at = utcnow()
    if case.assigned_to is None:
        case.assigned_to = actor.id

    db.add(
        CaseNote(
            case_id=case.id,
            author_id=actor.id,
            body=f"[{label}] {payload.note.strip()}",
            kind="decision",
        )
    )
    _event(
        db,
        case,
        "decision",
        f"{actor.full_name} ghi nhận kết luận: {label}",
        actor,
        {"decision": payload.decision, "note": payload.note.strip()},
    )
    log_action(
        db,
        actor=actor,
        action="case.decision",
        entity_type="case",
        entity_id=case.id,
        after={"decision": payload.decision, "note": payload.note.strip(), "close_case": payload.close_case},
        request=request,
    )
    db.commit()
    db.refresh(case)
    detail = CaseDetail.model_validate(case)
    explanations = sorted(case.explanations, key=lambda item: item.created_at, reverse=True)
    if explanations:
        detail.latest_explanation = ExplanationOut.model_validate(explanations[0])
    return detail


@router.post("/{case_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def add_note(
    case_id: str,
    payload: NoteCreate,
    request: Request,
    actor: User = Depends(require_roles("admin", "analyst")),
    db: Session = Depends(get_db),
) -> NoteOut:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy case")
    note = CaseNote(
        case_id=case.id,
        author_id=actor.id,
        body=payload.body.strip(),
        kind=payload.kind,
    )
    db.add(note)
    case.updated_at = utcnow()
    _event(db, case, "note", f"{actor.full_name} thêm ghi chú", actor)
    log_action(
        db,
        actor=actor,
        action="case.note",
        entity_type="case",
        entity_id=case.id,
        after={"kind": payload.kind, "preview": payload.body.strip()[:160]},
        request=request,
    )
    db.commit()
    db.refresh(note)
    return NoteOut.model_validate(note)


@router.post("/{case_id}/explain", response_model=ExplanationOut)
def explain_case(
    case_id: str,
    request: Request,
    force: bool = False,
    actor: User = Depends(require_roles("admin", "analyst")),
    db: Session = Depends(get_db),
) -> Explanation:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy case")
    if force:
        latest = db.scalar(
            select(Explanation)
            .where(Explanation.case_id == case.id)
            .order_by(Explanation.created_at.desc())
            .limit(1)
        )
        if latest is not None:
            elapsed = (utcnow() - latest.created_at).total_seconds()
            if elapsed < settings.explain_cooldown_seconds:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Vừa tạo giải thích {int(elapsed)}s trước, thử lại sau "
                    f"{settings.explain_cooldown_seconds - int(elapsed)}s",
                )
    explanation = generate_explanation(db, case, actor, force=force)
    _event(
        db,
        case,
        "explanation",
        f"AI tạo bản giải thích ({explanation.provider}/{explanation.model})",
        actor,
        {"explanation_id": explanation.id, "provider": explanation.provider},
    )
    log_action(
        db,
        actor=actor,
        action="case.explain",
        entity_type="case",
        entity_id=case.id,
        after={"provider": explanation.provider, "model": explanation.model},
        request=request,
    )
    db.commit()
    db.refresh(explanation)
    return explanation
