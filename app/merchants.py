from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Merchant

HIGH_RISK_CATEGORIES = {"crypto", "gift_card", "gambling", "cash_advance"}
MEDIUM_RISK_CATEGORIES = {"electronics", "jewelry", "travel"}


def risk_tier_for(category: str) -> str:
    normalized = (category or "").strip().lower()
    if normalized in HIGH_RISK_CATEGORIES:
        return "high"
    if normalized in MEDIUM_RISK_CATEGORIES:
        return "medium"
    return "low"


def get_or_create_merchant(db: Session, name: str, category: str, country: str = "VN") -> Merchant:
    """Trả về merchant theo tên (không phân biệt hoa/thường), tạo mới nếu chưa có.

    Thông tin master (category/country/risk_tier) chỉ được ghi lần đầu; snapshot
    trên từng giao dịch vẫn giữ nguyên giá trị tại thời điểm ingest.
    """
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("merchant_name không được rỗng")

    merchant = db.scalar(
        select(Merchant).where(func.lower(Merchant.name) == cleaned.lower())
    )
    if merchant is not None:
        return merchant

    merchant = Merchant(
        name=cleaned,
        category=(category or "other").strip().lower(),
        country=(country or "VN").strip().upper()[:2],
        risk_tier=risk_tier_for(category),
    )
    db.add(merchant)
    db.flush()
    return merchant
