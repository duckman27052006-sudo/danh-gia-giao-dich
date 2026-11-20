from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login


def _night_occurred_at() -> datetime:
    local_now = datetime.now(timezone.utc) + timedelta(hours=7)
    local = local_now.replace(hour=2, minute=15, second=0, microsecond=0)
    if local > local_now:
        local -= timedelta(days=1)
    return local - timedelta(hours=7)


def suspicious_payload(external_id: str | None = None) -> dict:
    return {
        "external_id": external_id or f"TEST-{uuid.uuid4().hex[:12]}",
        "customer_id": f"CUS-TEST-{uuid.uuid4().hex[:6]}",
        "customer_name": "Khách Hàng Kiểm Thử",
        "amount": 28_500_000,
        "channel": "online",
        "merchant_name": "Binance",
        "merchant_category": "crypto",
        "merchant_country": "SC",
        "card_country": "VN",
        "ip_country": "RU",
        "device_id": f"dev-test-{uuid.uuid4().hex[:6]}",
        "occurred_at": _night_occurred_at().isoformat(),
    }


def _create_case(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/api/transactions", json=suspicious_payload(), headers=headers)
    assert response.status_code == 201, response.text
    txn = response.json()
    assert txn["is_flagged"] is True, txn
    assert txn["case"] is not None
    detail = client.get(f"/api/cases/{txn['case']['id']}", headers=headers)
    assert detail.status_code == 200
    return detail.json()


def test_login_me_and_refresh(client: TestClient) -> None:
    headers = login(client, "admin@fraudlens.vn", "Admin@12345")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["email"] == "admin@fraudlens.vn"
    assert "fl_refresh" in client.cookies


def test_login_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "admin@fraudlens.vn", "password": "sai-mat-khau"}
    )
    assert response.status_code == 401


def test_viewer_is_read_only(client: TestClient, viewer_headers: dict[str, str]) -> None:
    assert client.get("/api/cases", headers=viewer_headers).status_code == 200
    assert client.get("/api/dashboard", headers=viewer_headers).status_code == 200
    assert client.get("/api/settings", headers=viewer_headers).status_code == 200
    assert client.post("/api/transactions/simulate", headers=viewer_headers, json={"count": 1}).status_code == 403
    assert client.get("/api/users", headers=viewer_headers).status_code == 403


def test_ingest_creates_flagged_case_and_audit(
    client: TestClient, analyst_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    case = _create_case(client, analyst_headers)
    txn = case["transaction"]
    assert case["risk_score"] >= 55
    assert txn["risk_band"] in {"high", "critical"}
    assert len(txn["rule_hits"]) >= 2
    assert txn["ml_score"] > 0
    assert txn["contributions"]
    assert case["events"][0]["type"] == "created"

    audit = client.get("/api/audit?page_size=100", headers=admin_headers)
    assert audit.status_code == 200
    actions = [item["action"] for item in audit.json()["items"]]
    assert "transaction.ingest" in actions


def test_decision_requires_confirmation_and_is_final(
    client: TestClient, analyst_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    case = _create_case(client, analyst_headers)
    case_id = case["id"]

    no_confirm = client.post(
        f"/api/cases/{case_id}/decision",
        headers=analyst_headers,
        json={"decision": "false_positive", "note": "Khách hàng xác nhận giao dịch hợp lệ.", "confirm": False},
    )
    assert no_confirm.status_code == 400

    short_note = client.post(
        f"/api/cases/{case_id}/decision",
        headers=analyst_headers,
        json={"decision": "false_positive", "note": "ngan", "confirm": True},
    )
    assert short_note.status_code == 422

    ok = client.post(
        f"/api/cases/{case_id}/decision",
        headers=analyst_headers,
        json={
            "decision": "false_positive",
            "note": "Đã gọi khách hàng, xác nhận giao dịch mua trang sức hợp lệ.",
            "confirm": True,
        },
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["status"] == "resolved"
    assert body["decision"] == "false_positive"
    assert body["resolved_at"] is not None

    duplicate = client.post(
        f"/api/cases/{case_id}/decision",
        headers=analyst_headers,
        json={
            "decision": "confirmed_fraud",
            "note": "Cố ghi đè kết luận đã lưu trước đó.",
            "confirm": True,
        },
    )
    assert duplicate.status_code == 409

    audit = client.get("/api/audit?page_size=100", headers=admin_headers)
    assert any(item["action"] == "case.decision" for item in audit.json()["items"])


def test_ai_explanation_offline_shape(client: TestClient, analyst_headers: dict[str, str]) -> None:
    case = _create_case(client, analyst_headers)
    first = client.post(f"/api/cases/{case['id']}/explain?force=true", headers=analyst_headers)
    assert first.status_code == 200, first.text
    explanation = first.json()
    assert explanation["provider"] == "offline"
    content = explanation["content"]
    assert content["summary"]
    assert len(content["why_flagged"]) >= 2
    assert len(content["verification_questions"]) >= 3
    assert "không phải kết luận" in content["disclaimer"]
    assert explanation["signals"]

    second = client.post(f"/api/cases/{case['id']}/explain", headers=analyst_headers)
    assert second.status_code == 200
    assert second.json()["id"] == explanation["id"]


def test_explanation_routes_to_openrouter(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, analyst_headers: dict[str, str]
) -> None:
    """OpenRouter dùng chung endpoint /chat/completions; test bằng HTTP giả lập."""
    import json as jsonlib

    from app import explain
    from app.config import settings

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "or-test-key")
    monkeypatch.setattr(settings, "ai_model", "openai/gpt-4o-mini")
    monkeypatch.setattr(settings, "ai_base_url", "")

    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            content = {
                "summary": "Tóm tắt do LLM sinh cho case kiểm thử.",
                "why_flagged": ["Số tiền lớn bất thường", "Thiết bị mới"],
                "normal_comparison": "Chi tiêu cao hơn nhiều so với 30 ngày trước.",
                "verification_questions": ["Anh/chị xác nhận giao dịch này?", "Thiết bị này là của anh/chị?"],
                "draft_note": "Đã ghi nhận, chờ khách hàng phản hồi.",
            }
            return {"choices": [{"message": {"content": jsonlib.dumps(content, ensure_ascii=False)}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["body"] = kwargs.get("json", {})
        return FakeResponse()

    monkeypatch.setattr(explain.httpx, "post", fake_post)

    case = _create_case(client, analyst_headers)
    response = client.post(f"/api/cases/{case['id']}/explain?force=true", headers=analyst_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "openrouter"
    assert body["model"] == "openai/gpt-4o-mini"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer or-test-key"
    assert captured["body"]["model"] == "openai/gpt-4o-mini"
    assert "LLM sinh" in body["content"]["summary"]

    status = client.get("/api/system/status", headers=analyst_headers).json()
    assert status["ai"] == {
        "configured": True,
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "base_url": "https://openrouter.ai/api/v1",
        "enabled": True,
    }


def test_explanation_falls_back_to_next_free_model(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, analyst_headers: dict[str, str]
) -> None:
    """Free tier hay trả 429: model chính lỗi thì tự chuyển sang model dự phòng."""
    from app import explain
    from app.config import settings

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "or-test-key")
    monkeypatch.setattr(settings, "ai_model", "openrouter/free")
    monkeypatch.setattr(settings, "ai_fallback_models", "baidu/ernie-5.5-flash-preview:free")
    monkeypatch.setattr(settings, "ai_base_url", "")

    calls: list[str] = []

    def fake_compat(info: explain.AIProviderInfo, prompt: str):
        calls.append(info.model)
        if info.model == "openrouter/free":
            raise RuntimeError("Client error '429 Too Many Requests'")
        return (
            {
                "summary": "Tóm tắt từ model dự phòng.",
                "why_flagged": ["Tín hiệu 1", "Tín hiệu 2"],
                "normal_comparison": "So với 30 ngày trước.",
                "verification_questions": ["Câu hỏi 1?", "Câu hỏi 2?"],
                "draft_note": "Ghi chú nháp.",
            },
            info.name,
            info.model,
        )

    monkeypatch.setattr(explain, "_call_openai_compatible", fake_compat)

    case = _create_case(client, analyst_headers)
    response = client.post(f"/api/cases/{case['id']}/explain?force=true", headers=analyst_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert calls == ["openrouter/free", "baidu/ernie-5.5-flash-preview:free"]
    assert body["model"] == "baidu/ernie-5.5-flash-preview:free"
    assert body["provider"] == "openrouter"
    assert body["content"]["summary"] == "Tóm tắt từ model dự phòng."


def test_security_headers_and_csp(client: TestClient) -> None:
    api = client.get("/api/health")
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["x-frame-options"] == "DENY"
    assert api.headers["cache-control"] == "no-store"

    page = client.get("/")
    assert page.status_code == 200
    csp = page.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_production_rejects_unsafe_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main as app_main
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", "dev-only-change-me-in-production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        app_main._validate_production_config()

    monkeypatch.setattr(settings, "jwt_secret", "x" * 40)
    monkeypatch.setattr(settings, "cookie_secure", False)
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        app_main._validate_production_config()

    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "demo_mode", False)
    app_main._validate_production_config()


def test_explain_regeneration_is_rate_limited(client: TestClient, analyst_headers: dict[str, str]) -> None:
    case = _create_case(client, analyst_headers)
    first = client.post(f"/api/cases/{case['id']}/explain?force=true", headers=analyst_headers)
    assert first.status_code == 200
    again = client.post(f"/api/cases/{case['id']}/explain?force=true", headers=analyst_headers)
    assert again.status_code == 429
    cached = client.post(f"/api/cases/{case['id']}/explain", headers=analyst_headers)
    assert cached.status_code == 200
    assert cached.json()["id"] == first.json()["id"]


def test_seed_explanation_never_calls_llm(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, analyst_headers: dict[str, str]
) -> None:
    """Seed phải dùng template offline: khởi động nhanh, không đốt quota AI."""
    from app import explain
    from app.config import settings
    from app.db import SessionLocal
    from app.models import Case

    monkeypatch.setattr(settings, "openrouter_api_key", "or-test-key")
    monkeypatch.setattr(settings, "ai_provider", "openrouter")
    called: list[int] = []
    monkeypatch.setattr(explain, "_call_provider", lambda *a, **k: called.append(1))

    case = _create_case(client, analyst_headers)
    with SessionLocal() as db:
        entity = db.get(Case, case["id"])
        assert entity is not None
        explanation = explain.generate_explanation(db, entity, None, force=True, use_llm=False)
        db.commit()
        assert explanation.provider == "offline"
    assert called == []


def test_case_note_and_timeline(client: TestClient, analyst_headers: dict[str, str]) -> None:
    case = _create_case(client, analyst_headers)
    note = client.post(
        f"/api/cases/{case['id']}/notes",
        headers=analyst_headers,
        json={"body": "Đã gửi email xác minh cho khách hàng.", "kind": "note"},
    )
    assert note.status_code == 201
    detail = client.get(f"/api/cases/{case['id']}", headers=analyst_headers).json()
    assert any(item["body"].startswith("Đã gửi email") for item in detail["notes"])
    assert any(item["type"] == "note" for item in detail["events"])


def test_rule_crud_and_rbac(
    client: TestClient, admin_headers: dict[str, str], analyst_headers: dict[str, str]
) -> None:
    payload = {
        "name": "Test rule số tiền rất lớn",
        "description": "Rule kiểm thử",
        "conditions": [{"field": "amount", "op": ">", "value": 100_000_000}],
        "weight": 30,
        "severity": "high",
        "category": "test",
        "enabled": True,
    }
    forbidden = client.post("/api/rules", headers=analyst_headers, json=payload)
    assert forbidden.status_code == 403

    created = client.post("/api/rules", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    updated = client.patch(f"/api/rules/{rule_id}", headers=admin_headers, json={"enabled": False, "weight": 10})
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    invalid = client.post(
        "/api/rules",
        headers=admin_headers,
        json={**payload, "conditions": [{"field": "unknown_field", "op": ">", "value": 1}]},
    )
    assert invalid.status_code == 422

    deleted = client.delete(f"/api/rules/{rule_id}", headers=admin_headers)
    assert deleted.status_code == 204


def test_dashboard_shape(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/dashboard?days=30", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    for key in ("summary", "trend", "channels", "categories", "score_bands", "priority_queue", "recent_alerts"):
        assert key in data
    assert data["summary"]["model_auc"] > 0.7
    assert len(data["trend"]) == 30


def test_simulate_returns_scored_transactions(client: TestClient, analyst_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/transactions/simulate",
        headers=analyst_headers,
        json={"count": 4, "fraud_bias": 1.0, "seed": 1},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 4
    assert len(body["items"]) == 4
    assert all(0 <= item["risk_score"] <= 100 for item in body["items"])
