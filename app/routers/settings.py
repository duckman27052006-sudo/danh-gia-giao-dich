from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import log_action
from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_roles
from app.explain import resolve_ai_provider
from app.ml.service import model_info
from app.models import Setting, User
from app.schemas import ModelInfo, SettingsOut, SettingsUpdate
from app.scoring import get_settings_row

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
def get_settings_endpoint(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Setting:
    return get_settings_row(db)


@router.patch("/settings", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    request: Request,
    actor: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> Setting:
    if payload.high_threshold <= payload.review_threshold:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Ngưỡng rủi ro cao phải lớn hơn ngưỡng cảnh báo",
        )
    if abs((payload.ml_weight + payload.rule_weight) - 1.0) > 0.001:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tổng trọng số ML + rule phải bằng 1")

    row = get_settings_row(db)
    before = {
        "review_threshold": row.review_threshold,
        "high_threshold": row.high_threshold,
        "ml_weight": row.ml_weight,
        "rule_weight": row.rule_weight,
        "ai_enabled": row.ai_enabled,
    }
    row.review_threshold = payload.review_threshold
    row.high_threshold = payload.high_threshold
    row.ml_weight = payload.ml_weight
    row.rule_weight = payload.rule_weight
    row.ai_enabled = payload.ai_enabled
    log_action(
        db,
        actor=actor,
        action="settings.update",
        entity_type="settings",
        entity_id="1",
        before=before,
        after=payload.model_dump(),
        request=request,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/model/info", response_model=ModelInfo)
def get_model_info(_: User = Depends(get_current_user)) -> dict:
    return model_info()


@router.get("/system/status")
def system_status(_: User = Depends(get_current_user)) -> dict:
    provider = resolve_ai_provider()
    return {
        "environment": settings.environment,
        "ai": {
            "configured": provider is not None,
            "provider": provider.name if provider else "offline",
            "model": provider.model if provider else "template-v1",
            "base_url": provider.base_url if provider else "",
            "enabled": settings.ai_enabled,
        },
        "demo_mode": settings.demo_mode,
        "model": {
            "version": model_info()["version"],
            "auc": model_info()["auc"],
        },
    }
