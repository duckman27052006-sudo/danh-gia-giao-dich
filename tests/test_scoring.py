"""Test cho cơ chế chấm điểm: hai ngưỡng thành phần và occlusion attribution."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import Rule
from app.scoring import get_settings_row, score_context

BENIGN_CONTEXT = {
    "amount": 45_000,
    "channel": "pos",
    "merchant_category": "grocery",
    "card_country": "VN",
    "ip_country": "VN",
    "hour": 11,
    "is_night": False,
    "country_mismatch": False,
    "new_device": False,
    "velocity_1h": 1,
    "velocity_24h": 1,
    "amount_ratio": 1.0,
    "distinct_merchants_24d": 1,
    "account_age_days": 400,
}


def test_ml_signal_alone_can_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trước đây ML 72 điểm + 0 rule = 39.6 (dưới ngưỡng 55) nên không gắn cờ."""
    monkeypatch.setattr("app.scoring.predict_probability", lambda _ctx: 0.72)
    with SessionLocal() as db:
        settings_row = get_settings_row(db)
        settings_row.ml_flag_probability = 0.65
        settings_row.rule_flag_threshold = 80
        ml_score, hits, rule_score, risk_score, _, band, flagged, reasons = score_context(
            db, dict(BENIGN_CONTEXT), settings_row
        )

    assert hits == []
    assert rule_score == 0.0
    assert ml_score == 72.0
    # Blend thuần = 39.6; điểm cuối phải giữ được tín hiệu ML đã vượt cổng.
    assert risk_score == 72.0
    assert flagged is True
    assert band == "high"
    assert "ml" in reasons


def test_rule_signal_alone_can_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule mạnh + model thấp vẫn phải vào hàng chờ (trước đây tối đa 45 điểm)."""
    monkeypatch.setattr("app.scoring.predict_probability", lambda _ctx: 0.02)
    with SessionLocal() as db:
        rule = Rule(
            name="Rule kiểm thử cổng rule",
            description="Tạm thời, test tự xoá",
            conditions=[{"field": "amount", "op": ">", "value": 1}],
            weight=100,
            severity="high",
            category="test",
            enabled=True,
        )
        db.add(rule)
        db.commit()
        try:
            settings_row = get_settings_row(db)
            settings_row.ml_flag_probability = 0.65
            settings_row.rule_flag_threshold = 80
            _, _, rule_score, risk_score, _, band, flagged, reasons = score_context(
                db, dict(BENIGN_CONTEXT), settings_row
            )
            assert rule_score == 100.0
            assert risk_score == 100.0
            assert flagged is True
            assert band == "critical"
            assert "rule" in reasons
        finally:
            db.delete(rule)
            db.commit()


def test_below_both_gates_keeps_blend_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không tín hiệu nào vượt cổng → điểm cuối đúng bằng công thức blend cũ."""
    monkeypatch.setattr("app.scoring.predict_probability", lambda _ctx: 0.20)
    with SessionLocal() as db:
        settings_row = get_settings_row(db)
        settings_row.ml_flag_probability = 0.65
        settings_row.rule_flag_threshold = 80
        ml_score, hits, rule_score, risk_score, _, band, flagged, _ = score_context(
            db, dict(BENIGN_CONTEXT), settings_row
        )

    assert hits == []
    assert rule_score == 0.0
    expected = round(
        ml_score * (settings_row.ml_weight / (settings_row.ml_weight + settings_row.rule_weight))
        + rule_score * (settings_row.rule_weight / (settings_row.ml_weight + settings_row.rule_weight)),
        1,
    )
    assert risk_score == expected
    assert flagged is False
    assert band in {"low", "medium"}


def test_settings_reject_gate_below_review_threshold(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    payload = client.get("/api/settings", headers=admin_headers).json()
    too_low = {**payload, "ml_flag_probability": 0.40, "review_threshold": 55}
    response = client.patch("/api/settings", headers=admin_headers, json=too_low)
    assert response.status_code == 422, response.text


def test_settings_expose_and_update_flag_gates(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    payload = client.get("/api/settings", headers=admin_headers).json()
    assert 0 < payload["ml_flag_probability"] <= 1
    assert payload["rule_flag_threshold"] >= payload["review_threshold"]

    updated = client.patch(
        "/api/settings",
        headers=admin_headers,
        json={
            **payload,
            "ml_flag_probability": 0.70,
            "rule_flag_threshold": 85,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["ml_flag_probability"] == pytest.approx(0.70)
    assert updated.json()["rule_flag_threshold"] == pytest.approx(85)

    restored = client.patch("/api/settings", headers=admin_headers, json=payload)
    assert restored.status_code == 200, restored.text


class _FakeModel:
    """Model giả: chỉ phản ứng với feature đầu tiên (amount_log)."""

    threshold = 10.0

    def predict_proba(self, matrix):
        return [[0.1, 0.9] if row[0] > self.threshold else [0.9, 0.1] for row in matrix]


def test_contributions_follow_occlusion_not_global_importance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature làm tăng xác suất phải báo hướng 'up' và chiếm phần lớn đóng góp."""
    monkeypatch.setattr(
        "app.ml.service.load_artifact",
        lambda: {"model": _FakeModel(), "metadata": {}},
    )
    monkeypatch.setattr(
        "app.ml.service.metadata",
        lambda: {"baseline": {"amount_log": {"mean": 8.0, "std": 1.0}}},
    )

    from app.ml.service import contributions

    # amount = 90.000.000 → amount_log ≈ 18.3 > 10 → model giả trả p=0.9 khi giữ,
    # và p=0.1 khi bị che về baseline 8.0. Đóng góp phải dồn hết vào "amount".
    items = contributions({**BENIGN_CONTEXT, "amount": 90_000_000}, risk_score=90)
    assert items
    top = items[0]
    assert top["feature"] == "amount"
    assert top["direction"] == "up"
    assert top["impact"] > 90


def test_contributions_empty_when_model_is_indifferent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FlatModel:
        def predict_proba(self, matrix):
            return [[0.5, 0.5] for _ in matrix]

    monkeypatch.setattr("app.ml.service.load_artifact", lambda: {"model": _FlatModel(), "metadata": {}})
    monkeypatch.setattr("app.ml.service.metadata", lambda: {"baseline": {}})

    from app.ml.service import contributions

    assert contributions(dict(BENIGN_CONTEXT), risk_score=0) == []
