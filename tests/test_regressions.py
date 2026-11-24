"""Test hồi quy cho các lỗi đã sửa ở "Chặng 0".

Mỗi test ở đây tương ứng một lỗi có thật đã được phát hiện khi audit:
cookie logout không bị xoá, filter ngày lệch múi giờ, PATCH rule với điều kiện
rỗng gây 500, `model_version` hardcode, `/api/health` lộ chi tiết lỗi, và
production chấp nhận DEMO_MODE mà không cần opt-in.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.ml.service import metadata
from app.timeutils import to_naive_utc
from tests.conftest import login


def _payload(occurred_at: datetime | None = None) -> dict:
    return {
        "external_id": f"REG-{uuid.uuid4().hex[:12]}",
        "customer_id": f"CUS-REG-{uuid.uuid4().hex[:6]}",
        "customer_name": "Khách Hồi Quy",
        "amount": 1_500_000,
        "channel": "pos",
        "merchant_name": "Siêu thị Hồi Quy",
        "merchant_category": "grocery",
        "merchant_country": "VN",
        "card_country": "VN",
        "ip_country": "VN",
        "device_id": f"dev-reg-{uuid.uuid4().hex[:6]}",
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
    }


def test_to_naive_utc_converts_offset_instead_of_dropping_it() -> None:
    """`.replace(tzinfo=None)` làm lệch 7 giờ; helper phải quy đổi sang UTC."""
    aware = datetime(2026, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    assert to_naive_utc(aware) == datetime(2025, 12, 31, 17, 0)
    naive = datetime(2026, 1, 1, 0, 0)
    assert to_naive_utc(naive) == naive


def test_date_filter_uses_utc_not_wall_clock(
    client: TestClient, analyst_headers: dict[str, str]
) -> None:
    """Mốc lọc gửi kèm offset +07:00 phải được hiểu là cùng một thời điểm UTC."""
    occurred_at = datetime(2026, 11, 1, 12, 0)
    created = client.post("/api/transactions", headers=analyst_headers, json=_payload(occurred_at))
    assert created.status_code == 201, created.text
    txn = created.json()

    # 19:00+07:00 chính là 12:00 UTC — đúng bằng thời điểm giao dịch.
    same_instant = (occurred_at + timedelta(hours=7)).replace(tzinfo=timezone(timedelta(hours=7)))
    listed = client.get(
        "/api/transactions",
        headers=analyst_headers,
        params={"customer_id": txn["customer_id"], "date_from": same_instant.isoformat()},
    )
    assert listed.status_code == 200, listed.text
    ids = [item["id"] for item in listed.json()["items"]]
    assert txn["id"] in ids, "Giao dịch đúng thời điểm bị loại vì filter hiểu sai múi giờ"

    # Một giây sau mốc thì phải bị loại (kiểm tra chiều ngược lại).
    just_after = (same_instant + timedelta(seconds=1)).isoformat()
    after = client.get(
        "/api/transactions",
        headers=analyst_headers,
        params={"customer_id": txn["customer_id"], "date_from": just_after},
    )
    assert txn["id"] not in [item["id"] for item in after.json()["items"]]


def test_logout_clears_refresh_cookie(client: TestClient) -> None:
    login(client, "analyst@fraudlens.vn", "Analyst@123")
    assert "fl_refresh" in client.cookies

    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    # Header phải nằm trên response trả về, nếu không trình duyệt giữ cookie cũ.
    assert "set-cookie" in response.headers
    assert "fl_refresh" in response.headers["set-cookie"]

    # Sau khi logout, refresh token cũ đã bị thu hồi.
    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 401


def test_patch_rule_with_empty_conditions_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    payload = {
        "name": "Rule điều kiện rỗng",
        "description": "Kiểm thử validation",
        "conditions": [{"field": "amount", "op": ">", "value": 50_000_000}],
        "weight": 20,
        "severity": "medium",
        "category": "test",
        "enabled": True,
    }
    created = client.post("/api/rules", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    empty = client.patch(f"/api/rules/{rule_id}", headers=admin_headers, json={"conditions": []})
    # Trước đây: lọt validation rồi đâm CHECK constraint → 500 và mất audit.
    assert empty.status_code == 422, empty.text

    still_there = client.get("/api/rules", headers=admin_headers).json()
    rule = next(item for item in still_there if item["id"] == rule_id)
    assert len(rule["conditions"]) == 1

    client.delete(f"/api/rules/{rule_id}", headers=admin_headers)


def test_model_version_comes_from_artifact(
    client: TestClient, analyst_headers: dict[str, str]
) -> None:
    created = client.post("/api/transactions", headers=analyst_headers, json=_payload())
    assert created.status_code == 201, created.text
    assert created.json()["model_version"] == metadata()["version"]


def test_health_is_liveness_and_ready_checks_dependencies(client: TestClient) -> None:
    live = client.get("/api/health")
    assert live.status_code == 200
    body = live.json()
    assert body["status"] == "ok"
    # Liveness không được rò thông tin hạ tầng ra ngoài.
    assert "database" not in body
    assert "model_auc" not in body

    ready = client.get("/api/health/ready")
    assert ready.status_code == 200, ready.text
    ready_body = ready.json()
    assert ready_body["status"] == "ready"
    assert ready_body["database"] == "postgresql"
    assert ready_body["model"] == metadata()["version"]


def test_production_requires_explicit_demo_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main as app_main
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", "x" * 40)
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "cors_origins", "https://fraudlens.example.com")
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "allow_demo_in_production", False)

    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        app_main._validate_production_config()

    monkeypatch.setattr(settings, "allow_demo_in_production", True)
    app_main._validate_production_config()

    monkeypatch.setattr(settings, "demo_mode", False)
    app_main._validate_production_config()
