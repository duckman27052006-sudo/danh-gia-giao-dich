from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.config import settings
from app.features import FEATURE_LABELS, FEATURE_NAMES, feature_vector

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def artifact_paths(base: Path | None = None) -> tuple[Path, Path]:
    directory = base or settings.model_dir
    return directory / "model.joblib", directory / "metadata.json"


def load_artifact() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        model_file, meta_file = artifact_paths()
        if not model_file.exists() or not meta_file.exists():
            from app.ml.train import train_and_save

            train_and_save()
        _cache = {
            "model": joblib.load(model_file),
            "metadata": json.loads(meta_file.read_text(encoding="utf-8")),
        }
        return _cache


def metadata() -> dict[str, Any]:
    return load_artifact()["metadata"]


def predict_probability(ctx: dict[str, Any]) -> float:
    model = load_artifact()["model"]
    vector = np.array([feature_vector(ctx)], dtype=float)
    return float(model.predict_proba(vector)[0][1])


def _display(feature: str, ctx: dict[str, Any]) -> str:
    from app.features import CATEGORY_LABELS, CHANNEL_LABELS, format_vnd

    if feature == "amount":
        return format_vnd(float(ctx.get("amount", 0)))
    if feature == "hour":
        return f"{int(ctx.get('hour', 0)):02d}:00"
    if feature in {"category", "category_risk"}:
        category = str(ctx.get("merchant_category", ""))
        return CATEGORY_LABELS.get(category, category)
    if feature in {"channel", "channel_online"}:
        channel = str(ctx.get("channel", ""))
        return CHANNEL_LABELS.get(channel, channel)
    if feature == "is_night":
        return "Có" if ctx.get("is_night") else "Không"
    if feature == "country_mismatch":
        return f"IP {ctx.get('ip_country')} / thẻ {ctx.get('card_country')}"
    if feature == "new_device":
        return "Thiết bị chưa từng thấy"
    if feature == "velocity_1h":
        return f"{ctx.get('velocity_1h', 1)} giao dịch / 60 phút"
    if feature == "velocity_24h":
        return f"{ctx.get('velocity_24h', 1)} giao dịch / 24 giờ"
    if feature == "amount_ratio":
        return f"×{float(ctx.get('amount_ratio', 1)):.1f} chi tiêu thường ngày"
    if feature == "distinct_merchants_24d":
        return f"{ctx.get('distinct_merchants_24d', 0)} merchant / 24 giờ"
    if feature == "account_age_days":
        return f"{int(ctx.get('account_age_days', 0))} ngày"
    return str(ctx.get(feature, ""))


# Gom các feature cùng nguồn lại để UI không hiện hai dòng cho cùng một tín hiệu.
FEATURE_GROUPS: dict[str, str] = {
    "amount_log": "amount",
    "hour_sin": "hour",
    "hour_cos": "hour",
    "amount_ratio_log": "amount_ratio",
    "channel_online": "channel",
    "category_risk": "category",
}

# Nhãn hiển thị lấy theo feature đại diện của nhóm.
GROUP_LABELS: dict[str, str] = {
    "amount": FEATURE_LABELS["amount_log"],
    "hour": FEATURE_LABELS["hour_sin"],
    "amount_ratio": FEATURE_LABELS["amount_ratio_log"],
    "channel": FEATURE_LABELS["channel_online"],
    "category": FEATURE_LABELS["category_risk"],
}


def contributions(ctx: dict[str, Any], risk_score: float, limit: int = 6) -> list[dict[str, Any]]:
    """Phân rã điểm rủi ro của CHÍNH giao dịch này bằng occlusion.

    Cách cũ là ``importance toàn cục × z-score``: nó không phụ thuộc model tại
    điểm dữ liệu đang xét nên **hướng đóng góp có thể ngược** với tác động thật
    (đo được: 62/120 trường hợp top-1 sai hướng) và luôn chuẩn hoá ~100% cho
    mọi giao dịch — kể cả giao dịch điểm 12/100.

    Cách hiện tại: thay từng feature bằng giá trị trung bình của tập huấn luyện,
    đo mức giảm xác suất fraud. Hiệu số ``p_hiện_tại - p_khi_che`` chính là đóng
    góp có dấu của feature đó (dương = đẩy rủi ro lên). Toàn bộ 13 phép che được
    gộp vào **một** lần gọi ``predict_proba`` nên chi phí gần như không đổi.

    Đây không phải SHAP (không có tính chất additive chuẩn tắc), nhưng đúng
    hướng theo định nghĩa và không cần thêm dependency.
    """
    meta = metadata()
    baseline = meta.get("baseline", {})
    model = load_artifact()["model"]

    vector = np.array(feature_vector(ctx), dtype=float)
    baseline_vector = np.array(
        [float(baseline.get(name, {}).get("mean", 0.0)) for name in FEATURE_NAMES], dtype=float
    )

    base_probability = float(np.asarray(model.predict_proba(vector.reshape(1, -1)))[0][1])
    masked = np.tile(vector, (len(FEATURE_NAMES), 1))
    for index in range(len(FEATURE_NAMES)):
        masked[index, index] = baseline_vector[index]
    masked_probabilities = np.asarray(model.predict_proba(masked))[:, 1]

    deltas: dict[str, float] = {}
    for index, name in enumerate(FEATURE_NAMES):
        group = FEATURE_GROUPS.get(name, name)
        delta = base_probability - float(masked_probabilities[index])
        # hour_sin/hour_cos là hai cách mã hoá cùng một tín hiệu → chia đôi để
        # không đếm gấp đôi đóng góp của giờ giao dịch.
        deltas[group] = deltas.get(group, 0.0) + (delta * 0.5 if group == "hour" else delta)

    total = sum(abs(value) for value in deltas.values())
    if total < 1e-12:
        return []

    items = []
    for feature, delta in deltas.items():
        items.append(
            {
                "feature": feature,
                "label": GROUP_LABELS.get(feature, FEATURE_LABELS.get(feature, feature)),
                "value": _display(feature, ctx),
                "impact": round(abs(delta) / total * 100, 1),
                "direction": "up" if delta >= 0 else "down",
            }
        )
    items.sort(key=lambda item: item["impact"], reverse=True)
    return items[:limit]


def model_info() -> dict[str, Any]:
    meta = metadata()
    return {
        "version": meta["version"],
        "trained_at": meta["trained_at"],
        "algorithm": meta["algorithm"],
        "auc": meta["auc"],
        "precision": meta["precision"],
        "recall": meta["recall"],
        "samples": meta["samples"],
        "feature_importance": meta["feature_importance"],
        "baseline": meta["baseline"],
    }
