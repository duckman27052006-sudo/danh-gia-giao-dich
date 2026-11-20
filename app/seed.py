from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.explain import generate_explanation
from app.features import CATEGORY_LABELS
from app.merchants import get_or_create_merchant, risk_tier_for
from app.ml.service import contributions, predict_probability
from app.ml.synthetic import generate_dataset
from app.models import (
    AuditLog,
    Case,
    CaseEvent,
    CaseNote,
    Merchant,
    Rule,
    Setting,
    Transaction,
    User,
    utcnow,
)
from app.rules import evaluate_rules
from app.scoring import priority_for
from app.security import hash_password

DEMO_USERS = [
    ("admin@fraudlens.vn", "Nguyễn Thu Hà", "Admin@12345", "admin"),
    ("analyst@fraudlens.vn", "Trần Minh Anh", "Analyst@123", "analyst"),
    ("analyst2@fraudlens.vn", "Lê Quốc Bảo", "Analyst@123", "analyst"),
    ("viewer@fraudlens.vn", "Phạm Ngọc Diệp", "Viewer@123", "viewer"),
]

SEED_RULES = [
    {
        "name": "Giao dịch giá trị lớn",
        "description": "Số tiền vượt 8 triệu đồng, cần kiểm tra khi khách hàng ít giao dịch lớn.",
        "conditions": [{"field": "amount", "op": ">", "value": 8_000_000}],
        "weight": 22,
        "severity": "high",
        "category": "amount",
    },
    {
        "name": "Giao dịch đêm giá trị cao",
        "description": "Giao dịch từ 23h đến 5h với giá trị trên 1,5 triệu đồng.",
        "conditions": [
            {"field": "is_night", "op": "==", "value": True},
            {"field": "amount", "op": ">", "value": 1_500_000},
        ],
        "weight": 14,
        "severity": "medium",
        "category": "time",
    },
    {
        "name": "Lệch quốc gia IP và thẻ",
        "description": "IP giao dịch khác quốc gia phát hành thẻ.",
        "conditions": [{"field": "country_mismatch", "op": "==", "value": True}],
        "weight": 18,
        "severity": "high",
        "category": "geo",
    },
    {
        "name": "Tần suất giao dịch cao",
        "description": "Từ 4 giao dịch trong 60 phút trở lên.",
        "conditions": [{"field": "velocity_1h", "op": ">=", "value": 4}],
        "weight": 20,
        "severity": "high",
        "category": "velocity",
    },
    {
        "name": "Thiết bị mới, giá trị cao",
        "description": "Thiết bị chưa từng thấy đi kèm giao dịch trên 1 triệu đồng.",
        "conditions": [
            {"field": "new_device", "op": "==", "value": True},
            {"field": "amount", "op": ">", "value": 1_000_000},
        ],
        "weight": 15,
        "severity": "medium",
        "category": "device",
    },
    {
        "name": "Dấu hiệu thử thẻ",
        "description": "Giao dịch online giá trị rất nhỏ, thường dùng để kiểm tra thẻ còn sống.",
        "conditions": [
            {"field": "amount", "op": "<", "value": 50_000},
            {"field": "channel", "op": "in", "value": ["online"]},
        ],
        "weight": 22,
        "severity": "high",
        "category": "card_testing",
    },
    {
        "name": "Ngành hàng rủi ro cao",
        "description": "Tiền mã hóa, thẻ quà tặng hoặc cá cược với giá trị trên 500 nghìn.",
        "conditions": [
            {"field": "merchant_category", "op": "in", "value": ["crypto", "gift_card", "gambling"]},
            {"field": "amount", "op": ">", "value": 500_000},
        ],
        "weight": 16,
        "severity": "medium",
        "category": "merchant",
    },
    {
        "name": "Chi tiêu vượt thói quen",
        "description": "Giá trị giao dịch gấp 5 lần mức trung bình 30 ngày.",
        "conditions": [{"field": "amount_ratio", "op": ">=", "value": 5}],
        "weight": 18,
        "severity": "medium",
        "category": "behavior",
    },
]

DECISION_NOTES = {
    "confirmed_fraud": [
        "Khách hàng xác nhận không thực hiện giao dịch. Đã khoá thẻ và chuyển hồ sơ sang bộ phận tranh chấp.",
        "Thiết bị và IP không thuộc khách hàng, OTP bị lộ. Xác nhận gian lận, đang thu hồi tiền.",
        "Merchant xác nhận đơn hàng gửi đến địa chỉ lạ. Chuyển hồ sơ điều tra chuyên sâu.",
    ],
    "false_positive": [
        "Khách hàng xác nhận đã mua hàng và dùng thiết bị mới. Đóng cảnh báo.",
        "Giao dịch hợp lệ trong chuyến công tác nước ngoài, khách đã xác nhận qua tổng đài.",
        "Khách thanh toán hóa đơn lớn định kỳ, không có dấu hiệu bất thường.",
    ],
    "escalated": [
        "Có dấu hiệu liên quan nhiều tài khoản, cần chuyển nhóm điều tra chuyên sâu.",
        "Khách hàng chưa phản hồi sau 2 lần liên hệ, chuyển cấp ưu tiên P1.",
    ],
}


def seed_rules(db: Session) -> list[Rule]:
    rules = []
    for item in SEED_RULES:
        rule = Rule(**item)
        db.add(rule)
        rules.append(rule)
    return rules


def seed_users(db: Session) -> list[User]:
    users = []
    for email, name, password, role in DEMO_USERS:
        user = User(
            email=email,
            full_name=name,
            role=role,
            password_hash=hash_password(password),
        )
        db.add(user)
        users.append(user)
    return users


def seed_merchants(db: Session) -> list[Merchant]:
    from app.ml.synthetic import MERCHANTS

    merchants: list[Merchant] = []
    seen = set()
    for name, category, country in MERCHANTS:
        if name in seen:
            continue
        seen.add(name)
        merchant = Merchant(
            name=name,
            category=category,
            country=country,
            risk_tier=risk_tier_for(category),
        )
        db.add(merchant)
        merchants.append(merchant)
    return merchants


def _score_record(record: dict, rules: list[Rule], setting: Setting) -> dict:
    ctx = dict(record)
    ctx["merchant_country"] = record.get("merchant_country", "VN")
    probability = predict_probability(ctx)
    ml_score = round(probability * 100, 1)
    rule_score, hits = evaluate_rules(rules, ctx)
    risk_score = round(ml_score * setting.ml_weight + rule_score * setting.rule_weight, 1)
    risk_score = max(0.0, min(risk_score, 100.0))
    if risk_score >= setting.high_threshold:
        band = "critical"
    elif risk_score >= setting.review_threshold:
        band = "high"
    elif risk_score >= setting.review_threshold * 0.65:
        band = "medium"
    else:
        band = "low"
    for rule in rules:
        if any(hit["rule_id"] == rule.id for hit in hits):
            rule.hit_count += 1
    return {
        "ml_score": ml_score,
        "rule_score": rule_score,
        "risk_score": risk_score,
        "risk_band": band,
        "rule_hits": hits,
        "contributions": contributions(ctx, risk_score),
        "is_flagged": risk_score >= setting.review_threshold,
    }


def seed_transactions(
    db: Session,
    rules: list[Rule],
    setting: Setting,
    analysts: list[User],
    merchants: list[Merchant] | None = None,
) -> list[Case]:
    records = generate_dataset(
        seed=17,
        days=30,
        customers=150,
        fraud_events_per_customer=0.028,
        anomaly_rate=0.012,
        start=utcnow(),
    )
    now = utcnow()
    pending: list[tuple[Transaction, dict]] = []
    # Đảm bảo merchant/user/rule đang chờ đã có id trước khi tham chiếu.
    db.flush()
    merchant_ids = {merchant.name: merchant.id for merchant in (merchants or [])}
    if not merchant_ids:
        merchant_ids = {
            merchant.name: merchant.id
            for merchant in db.scalars(select(Merchant)).all()
        }

    for record in records:
        scored = _score_record(record, rules, setting)
        occurred_at = record["occurred_at"]
        if occurred_at.tzinfo is not None:
            occurred_at = occurred_at.replace(tzinfo=None)
        merchant_id = merchant_ids.get(record["merchant_name"])
        if merchant_id is None:
            merchant = get_or_create_merchant(
                db,
                record["merchant_name"],
                record["merchant_category"],
                record.get("merchant_country", "VN"),
            )
            merchant_ids[merchant.name] = merchant.id
            merchant_id = merchant.id
        txn = Transaction(
            external_id=record["external_id"],
            customer_id=record["customer_id"],
            customer_name=record["customer_name"],
            amount=record["amount"],
            currency="VND",
            channel=record["channel"],
            merchant_id=merchant_id,
            merchant_name=record["merchant_name"],
            merchant_category=record["merchant_category"],
            merchant_country=record.get("merchant_country", "VN"),
            card_country="VN",
            ip_country=record["ip_country"],
            device_id=record["device_id"],
            occurred_at=occurred_at,
            ingested_at=occurred_at,
            hour=int(record["hour"]),
            is_night=bool(record["is_night"]),
            country_mismatch=bool(record["country_mismatch"]),
            new_device=bool(record["new_device"]),
            velocity_1h=int(record["velocity_1h"]),
            velocity_24h=int(record["velocity_24h"]),
            amount_ratio=float(record["amount_ratio"]),
            distinct_merchants_24d=int(record["distinct_merchants_24d"]),
            account_age_days=int(record["account_age_days"]),
            model_version="gbdt-1.0.0",
            is_simulated=False,
            **scored,
        )
        db.add(txn)
        pending.append((txn, record))

    db.flush()
    year = now.year
    sequence = 0
    rng = random.Random(23)
    cases: list[Case] = []

    for txn, _record in pending:
        if not txn.is_flagged:
            continue
        sequence += 1
        priority = priority_for(txn.risk_score, float(txn.amount), setting)
        sla_hours = {"P1": 4, "P2": 12, "P3": 48}[priority]
        age_days = (now - txn.occurred_at).days
        resolved = age_days >= 2 and rng.random() < 0.68
        status = "resolved" if resolved else rng.choices(
            ["open", "in_review", "awaiting_info"], weights=[55, 30, 15], k=1
        )[0]
        assigned = rng.choice(analysts) if (resolved or rng.random() < 0.6) else None
        # Case đang mở được đưa vào queue gần đây để SLA phản ánh vận hành thực tế.
        created_at = txn.occurred_at
        if not resolved:
            created_at = max(txn.occurred_at, now - timedelta(minutes=rng.uniform(15, sla_hours * 60 * 1.3)))
        case = Case(
            code=f"CASE-{year}-{sequence:04d}",
            transaction_id=txn.id,
            priority=priority,
            status=status,
            risk_score=txn.risk_score,
            assigned_to=assigned.id if assigned else None,
            sla_due_at=created_at + timedelta(hours=sla_hours),
            created_at=created_at,
            updated_at=created_at,
        )
        if resolved and assigned is not None:
            decision = rng.choices(
                ["confirmed_fraud", "false_positive", "escalated"], weights=[45, 45, 10], k=1
            )[0]
            hours = rng.uniform(0.4, 20 if priority != "P1" else 4)
            case.decision = decision
            case.decision_note = rng.choice(DECISION_NOTES[decision])
            case.resolved_at = created_at + timedelta(hours=hours)
            case.updated_at = case.resolved_at
            case.status = "resolved"
        db.add(case)
        cases.append(case)

    db.flush()
    for case in cases:
        db.add(
            CaseEvent(
                case_id=case.id,
                type="created",
                message=(
                    f"Hệ thống gắn cờ giao dịch với điểm rủi ro {case.risk_score:.0f}/100. "
                    "Chờ analyst xác minh."
                ),
                meta={"risk_score": case.risk_score, "priority": case.priority, "seeded": True},
                created_at=case.created_at,
            )
        )
        if case.decision:
            db.add(
                CaseNote(
                    case_id=case.id,
                    author_id=case.assigned_to,
                    body=f"[Kết luận] {case.decision_note}",
                    kind="decision",
                    created_at=case.resolved_at or case.created_at,
                )
            )
            db.add(
                CaseEvent(
                    case_id=case.id,
                    type="decision",
                    actor_id=case.assigned_to,
                    message=f"Ghi nhận kết luận: {case.decision}",
                    meta={"decision": case.decision, "seeded": True},
                    created_at=case.resolved_at or case.created_at,
                )
            )

    for case in cases:
        if case.decision and case.assigned_to:
            actor = next((user for user in analysts if user.id == case.assigned_to), None)
            db.add(
                AuditLog(
                    actor_id=case.assigned_to,
                    actor_email=actor.email if actor else "analyst@fraudlens.vn",
                    action="case.decision",
                    entity_type="case",
                    entity_id=case.id,
                    after={"decision": case.decision, "note": case.decision_note},
                    ip="127.0.0.1",
                    created_at=case.resolved_at or now,
                )
            )

    for rule in rules:
        db.add(
            AuditLog(
                actor_email="system",
                action="rule.create",
                entity_type="rule",
                entity_id=rule.id,
                after={"name": rule.name, "weight": rule.weight, "enabled": rule.enabled},
                created_at=now - timedelta(days=30),
            )
        )

    db.add(
        AuditLog(
            actor_email="system",
            action="settings.update",
            entity_type="settings",
            entity_id="1",
            after={
                "review_threshold": setting.review_threshold,
                "high_threshold": setting.high_threshold,
                "ml_weight": setting.ml_weight,
                "rule_weight": setting.rule_weight,
            },
            created_at=now - timedelta(days=30),
        )
    )

    db.add(
        AuditLog(
            actor_email="system",
            action="demo.seed",
            entity_type="system",
            entity_id="seed",
            after={"transactions": len(pending), "cases": len(cases)},
        )
    )
    db.commit()

    # Sinh sẵn bản giải thích offline cho 3 case P1 đang mở để demo UI.
    # Cố ý dùng template offline: seed phải chạy trong vài giây và không gọi LLM.
    top_open = sorted(
        [case for case in cases if case.status != "resolved"],
        key=lambda case: case.risk_score,
        reverse=True,
    )[:3]
    for case in top_open:
        db.refresh(case)
        if case.transaction is not None:
            generate_explanation(db, case, None, force=True, use_llm=False)
    db.commit()
    return cases


def seed_demo_data(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(User)) > 0:
        return

    setting = Setting(id=1, review_threshold=55, high_threshold=78, ml_weight=0.55, rule_weight=0.45)
    db.add(setting)
    users = seed_users(db)
    db.flush()
    analysts = [user for user in users if user.role == "analyst"]
    merchants = seed_merchants(db)
    rules = seed_rules(db)
    db.flush()
    seed_transactions(db, rules, setting, analysts, merchants)


def seed_summary(db: Session) -> dict:
    return {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "merchants": db.scalar(select(func.count()).select_from(Merchant)) or 0,
        "transactions": db.scalar(select(func.count()).select_from(Transaction)) or 0,
        "cases": db.scalar(select(func.count()).select_from(Case)) or 0,
        "rules": db.scalar(select(func.count()).select_from(Rule)) or 0,
        "categories": sorted(CATEGORY_LABELS),
    }


if __name__ == "__main__":
    from app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as session:
        seed_demo_data(session)
        print(seed_summary(session))
