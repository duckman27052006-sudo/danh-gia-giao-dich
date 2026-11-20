from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.features import CATEGORY_LABELS, CHANNEL_LABELS, format_vnd, local_hour
from app.models import Case, Explanation, Transaction, User
from app.scoring import get_settings_row

logger = logging.getLogger("fraudlens.ai")

DISCLAIMER = (
    "Đây là bản tóm tắt hỗ trợ điều tra do hệ thống tạo, không phải kết luận gian lận. "
    "Mọi quyết định cuối cùng phải do analyst xác minh và ghi nhận."
)

SYSTEM_PROMPT = """Bạn là trợ lý điều tra gian lận cho một ngân hàng số tại Việt Nam.
Nhiệm vụ: giải thích vì sao một giao dịch bị hệ thống chấm điểm rủi ro gắn cờ, dựa CHÍNH XÁC trên dữ liệu được cung cấp.
Tuyệt đối không khẳng định giao dịch là gian lận, không suy đoán ngoài dữ liệu, không bịa thêm giao dịch.
Giọng văn: tiếng Việt, ngắn gọn, chuyên nghiệp, dễ hiểu với nhân viên vận hành.
Trả về DUY NHẤT một JSON object với schema:
{
  "summary": "2-3 câu tóm tắt tình huống và mức rủi ro",
  "why_flagged": ["3-5 gạch đầu dòng nêu tín hiệu cụ thể kèm số liệu"],
  "normal_comparison": "1-2 câu so sánh với hành vi thông thường của khách hàng",
  "verification_questions": ["3-4 câu hỏi cụ thể để analyst xác minh với khách hàng"],
  "draft_note": "đoạn ghi chú nháp 2-4 câu cho analyst, nêu rõ chưa có kết luận"
}"""


def _history_stats(db: Session, txn: Transaction) -> dict[str, Any]:
    since = txn.occurred_at - timedelta(days=30)
    rows = db.execute(
        select(Transaction.merchant_category, Transaction.amount, Transaction.occurred_at)
        .where(
            Transaction.customer_id == txn.customer_id,
            Transaction.occurred_at < txn.occurred_at,
            Transaction.occurred_at >= since,
        )
        .order_by(Transaction.occurred_at.desc())
        .limit(300)
    ).all()
    if not rows:
        return {"count": 0, "avg_amount": float(txn.amount), "categories": [], "hours": []}
    avg_amount = sum(float(row.amount) for row in rows) / len(rows)
    categories: dict[str, int] = {}
    for row in rows:
        categories[row.merchant_category] = categories.get(row.merchant_category, 0) + 1
    top_categories = sorted(categories.items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "count": len(rows),
        "avg_amount": round(avg_amount, 2),
        "categories": [CATEGORY_LABELS.get(key, key) for key, _ in top_categories],
        "hours": sorted({local_hour(row.occurred_at) for row in rows}),
    }


def build_signals(case: Case, txn: Transaction, stats: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for hit in txn.rule_hits or []:
        signals.append(
            {
                "type": "rule",
                "label": hit.get("name", "Rule"),
                "detail": f"+{hit.get('weight', 0)} điểm rule · mức {hit.get('severity', 'medium')}",
                "weight": hit.get("weight", 0),
                "severity": hit.get("severity", "medium"),
            }
        )
    for contribution in (txn.contributions or [])[:4]:
        if contribution.get("direction") != "up":
            continue
        signals.append(
            {
                "type": "model",
                "label": contribution.get("label", "Tín hiệu model"),
                "detail": str(contribution.get("value", "")),
                "weight": contribution.get("impact", 0),
                "severity": "info",
            }
        )
    if stats.get("count"):
        signals.append(
            {
                "type": "context",
                "label": "Hành vi 30 ngày",
                "detail": (
                    f"{stats['count']} giao dịch · trung bình {format_vnd(stats['avg_amount'])}"
                ),
                "weight": 0,
                "severity": "info",
            }
        )
    return signals


def _why_flagged(txn: Transaction, stats: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    avg = float(stats.get("avg_amount") or (float(txn.amount) / max(txn.amount_ratio, 1.0)))
    ratio = float(txn.amount) / max(avg, 1.0)
    if ratio >= 2:
        reasons.append(
            f"Giá trị {format_vnd(float(txn.amount))} cao gấp {ratio:.1f} lần mức chi trung bình 30 ngày ({format_vnd(avg)})."
        )
    if txn.is_night:
        reasons.append(f"Giao dịch phát sinh lúc {txn.hour:02d}:00, nằm ngoài khung giờ sinh hoạt thường thấy.")
    if txn.country_mismatch:
        reasons.append(f"IP đến từ {txn.ip_country} trong khi thẻ phát hành tại {txn.card_country}.")
    if txn.new_device:
        reasons.append("Thiết bị dùng để giao dịch chưa từng xuất hiện trong lịch sử của khách hàng.")
    if txn.velocity_1h >= 3:
        reasons.append(f"Có {txn.velocity_1h} giao dịch trong 60 phút gần nhất, cao hơn nhịp thông thường.")
    if txn.merchant_category in {"crypto", "gift_card", "gambling", "cash_advance"}:
        reasons.append(
            f"Ngành hàng {CATEGORY_LABELS.get(txn.merchant_category, txn.merchant_category)} thường bị lợi dụng để rút tiền hoặc che giấu nguồn tiền."
        )
    for hit in sorted(txn.rule_hits or [], key=lambda item: item.get("weight", 0), reverse=True):
        if len(reasons) >= 5:
            break
        label = hit.get("name")
        if label and all(label not in reason for reason in reasons):
            reasons.append(f"Khớp rule “{label}” (+{hit.get('weight', 0)} điểm rule).")
    if not reasons:
        reasons.append("Tổ hợp tín hiệu hành vi khiến mô hình chấm điểm rủi ro cao hơn ngưỡng cảnh báo.")
    return reasons[:5]


def _offline_content(txn: Transaction, stats: dict[str, Any], category_label: str) -> dict[str, Any]:
    amount_text = format_vnd(float(txn.amount))
    band_label = {
        "critical": "rất cao",
        "high": "cao",
        "medium": "trung bình",
        "low": "thấp",
    }.get(txn.risk_band, txn.risk_band)
    avg = float(stats.get("avg_amount") or (float(txn.amount) / max(txn.amount_ratio, 1.0)))
    earlier = stats.get("count", 0)

    normal_comparison = (
        f"Trong 30 ngày trước, khách hàng có {earlier} giao dịch với giá trị trung bình {format_vnd(avg)}. "
        f"Giao dịch này là {amount_text} và thuộc nhóm {category_label}."
        if earlier
        else "Đây là giao dịch đầu tiên được ghi nhận của khách hàng trong 30 ngày, nên chưa có baseline hành vi đáng tin cậy."
    )

    questions: list[str] = [f"Anh/chị có nhận ra giao dịch {amount_text} tại {txn.merchant_name} không?"]
    if txn.country_mismatch:
        questions.append(
            f"Anh/chị có đang ở {txn.ip_country}, dùng VPN, hoặc vừa đăng nhập từ thiết bị lạ không?"
        )
    if txn.new_device:
        questions.append("Thiết bị thực hiện giao dịch có phải thiết bị anh/chị thường dùng không?")
    if txn.velocity_1h >= 3:
        questions.append("Các giao dịch liên tiếp trong vòng một giờ có phải do anh/chị chủ động thực hiện?")
    questions.append("Thông tin người thụ hưởng và địa chỉ nhận hàng có đúng với đăng ký không?")
    if txn.new_device or txn.country_mismatch:
        questions.append("Anh/chị có chia sẻ OTP, mật khẩu hoặc thông tin thẻ cho ai khác gần đây không?")

    draft_note = (
        f"Đã kiểm tra giao dịch {txn.external_id}: {amount_text} tại {txn.merchant_name} "
        f"({CHANNEL_LABELS.get(txn.channel, txn.channel)}), điểm rủi ro {txn.risk_score:.0f}/100. "
        f"Hệ thống ghi nhận {len(txn.rule_hits or [])} rule khớp và {earlier} giao dịch trong 30 ngày trước đó. "
        "Đã gửi câu hỏi xác minh cho khách hàng; chưa ghi nhận kết luận gian lận."
    )

    return {
        "summary": (
            f"Giao dịch {amount_text} tại {txn.merchant_name} bị gắn cờ với điểm rủi ro "
            f"{txn.risk_score:.0f}/100 (mức {band_label}). "
            f"Điểm ML {txn.ml_score:.0f}/100, điểm rule {txn.rule_score:.0f}/100; cần analyst xác minh trước khi kết luận."
        ),
        "why_flagged": _why_flagged(txn, stats),
        "normal_comparison": normal_comparison,
        "verification_questions": questions[:4],
        "draft_note": draft_note,
        "disclaimer": DISCLAIMER,
    }


def _prompt(txn: Transaction, stats: dict[str, Any], signals: list[dict[str, Any]]) -> str:
    facts = {
        "ma_giao_dich": txn.external_id,
        "so_tien_vnd": float(txn.amount),
        "thoi_diem_gio_dia_phuong": f"{txn.occurred_at.strftime('%d/%m/%Y')} {txn.hour:02d}:00",
        "kenh": CHANNEL_LABELS.get(txn.channel, txn.channel),
        "merchant": txn.merchant_name,
        "nganh_hang": CATEGORY_LABELS.get(txn.merchant_category, txn.merchant_category),
        "quoc_gia_merchant": txn.merchant_country,
        "quoc_gia_the": txn.card_country,
        "quoc_gia_ip": txn.ip_country,
        "thiet_bi_moi": txn.new_device,
        "so_giao_dich_1h": txn.velocity_1h,
        "so_giao_dich_24h": txn.velocity_24h,
        "so_lan_chi_tieu_trung_binh_30_ngay": txn.amount_ratio,
        "diem_ml": txn.ml_score,
        "diem_rule": txn.rule_score,
        "diem_rui_ro": txn.risk_score,
        "muc_rui_ro": txn.risk_band,
        "rule_khop": [hit.get("name") for hit in txn.rule_hits or []],
        "tin_hieu_model": [
            {"ten": item.get("label"), "gia_tri": item.get("value"), "muc_anh_huong": item.get("impact")}
            for item in (txn.contributions or [])[:5]
        ],
        "hanh_vi_30_ngay": {
            "so_giao_dich": stats.get("count"),
            "chi_tieu_trung_binh_vnd": stats.get("avg_amount"),
            "nganh_hang_quen_thuoc": stats.get("categories"),
        },
    }
    return (
        "Dữ liệu giao dịch bị gắn cờ (chỉ dùng dữ liệu này):\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
        "Yêu cầu: giải thích bằng tiếng Việt cho analyst, nêu tín hiệu cụ thể kèm số liệu, "
        "so sánh với hành vi 30 ngày, đặt câu hỏi xác minh thực tế và soạn ghi chú nháp. "
        "Không khẳng định gian lận. Trả về JSON đúng schema."
    )


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Không tìm thấy JSON trong phản hồi")
    return json.loads(match.group(0))


def _normalize_content(raw: dict[str, Any], txn: Transaction, stats: dict[str, Any], category_label: str) -> dict[str, Any]:
    fallback = _offline_content(txn, stats, category_label)
    why = raw.get("why_flagged")
    questions = raw.get("verification_questions")
    content = {
        "summary": str(raw.get("summary") or fallback["summary"]).strip(),
        "why_flagged": [str(item).strip() for item in why][:5] if isinstance(why, list) and why else fallback["why_flagged"],
        "normal_comparison": str(raw.get("normal_comparison") or fallback["normal_comparison"]).strip(),
        "verification_questions": (
            [str(item).strip() for item in questions][:4]
            if isinstance(questions, list) and questions
            else fallback["verification_questions"]
        ),
        "draft_note": str(raw.get("draft_note") or fallback["draft_note"]).strip(),
    }
    content["disclaimer"] = DISCLAIMER
    return content


DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com",
}


@dataclass(frozen=True)
class AIProviderInfo:
    name: str
    api_key: str
    base_url: str
    model: str


def resolve_ai_provider() -> AIProviderInfo | None:
    """Chọn provider AI đang dùng; ``None`` nghĩa là chỉ có template offline.

    ``AI_PROVIDER=auto`` ưu tiên OpenRouter → OpenAI → Anthropic theo key có sẵn.
    ``AI_BASE_URL`` cho phép trỏ sang gateway tương thích OpenAI (OpenRouter,
    Ollama, LM Studio, vLLM...).
    """
    choice = (settings.ai_provider or "auto").strip().lower()
    if choice == "offline":
        return None

    keys = {
        "openrouter": (settings.openrouter_api_key.strip(), settings.ai_model),
        "openai": (settings.openai_api_key.strip(), settings.ai_model),
        "anthropic": (settings.anthropic_api_key.strip(), settings.anthropic_model),
    }
    order = ["openrouter", "openai", "anthropic"] if choice == "auto" else [choice]
    base_override = settings.ai_base_url.strip()
    for name in order:
        entry = keys.get(name)
        if entry is None or not entry[0]:
            continue
        api_key, model = entry
        return AIProviderInfo(
            name=name,
            api_key=api_key,
            base_url=(base_override or DEFAULT_BASE_URLS[name]).rstrip("/"),
            model=model,
        )
    return None


def _call_openai_compatible(info: AIProviderInfo, prompt: str) -> tuple[dict[str, Any], str, str]:
    """Gọi endpoint /chat/completions kiểu OpenAI (OpenAI, OpenRouter, Ollama...)."""
    headers = {
        "Authorization": f"Bearer {info.api_key}",
        "Content-Type": "application/json",
    }
    if info.name == "openrouter":
        # OpenRouter dùng hai header này để gắn app trên dashboard; không bắt buộc.
        headers["HTTP-Referer"] = "https://fraudlens.local"
        headers["X-Title"] = "FraudLens"

    body: dict[str, Any] = {
        "model": info.model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    url = f"{info.base_url}/chat/completions"
    response = httpx.post(url, headers=headers, json=body, timeout=settings.ai_timeout_seconds)
    if response.status_code == 400 and "response_format" in body:
        # Một số model trên OpenRouter không hỗ trợ json_object → thử lại không kèm.
        body.pop("response_format")
        response = httpx.post(url, headers=headers, json=body, timeout=settings.ai_timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    return _extract_json(payload["choices"][0]["message"]["content"]), info.name, info.model


def _call_anthropic(info: AIProviderInfo, prompt: str) -> tuple[dict[str, Any], str, str]:
    response = httpx.post(
        f"{info.base_url}/v1/messages",
        headers={
            "x-api-key": info.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": info.model,
            "max_tokens": 1500,
            "temperature": 0.2,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=settings.ai_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    text = "".join(block.get("text", "") for block in payload.get("content", []))
    return _extract_json(text), info.name, info.model


def _call_provider(info: AIProviderInfo, prompt: str) -> tuple[dict[str, Any], str, str]:
    """Gọi model chính, nếu lỗi thì thử lần lượt các model trong AI_FALLBACK_MODELS."""
    if info.name == "anthropic":
        return _call_anthropic(info, prompt)

    models = [info.model]
    models += [item.strip() for item in settings.ai_fallback_models.split(",") if item.strip()]
    last_error: Exception | None = None
    for model in dict.fromkeys(models):
        candidate = info if model == info.model else replace(info, model=model)
        try:
            return _call_openai_compatible(candidate, prompt)
        except Exception as exc:  # thử model kế tiếp
            last_error = exc
            logger.warning("AI model %s lỗi (%s), thử model kế tiếp", model, exc)
    raise last_error or RuntimeError("Không gọi được model AI nào")


def generate_explanation(
    db: Session,
    case: Case,
    actor: User | None,
    *,
    force: bool = False,
    use_llm: bool = True,
) -> Explanation:
    """Tạo giải thích cho case.

    ``use_llm=False`` ép dùng template offline — dùng cho seed dữ liệu demo để
    khởi động nhanh và không đốt quota/chi phí gọi model.
    """
    existing = db.scalar(
        select(Explanation).where(Explanation.case_id == case.id).order_by(Explanation.created_at.desc()).limit(1)
    )
    if existing is not None and not force:
        return existing

    txn = case.transaction
    stats = _history_stats(db, txn)
    signals = build_signals(case, txn, stats)
    category_label = CATEGORY_LABELS.get(txn.merchant_category, txn.merchant_category)
    settings_row = get_settings_row(db)
    provider_info = resolve_ai_provider() if use_llm else None

    started = time.perf_counter()
    provider = "offline"
    model = "template-v1"
    content: dict[str, Any]
    if settings.ai_enabled and settings_row.ai_enabled and provider_info is not None:
        try:
            raw, provider, model = _call_provider(provider_info, _prompt(txn, stats, signals))
            content = _normalize_content(raw, txn, stats, category_label)
        except Exception as exc:
            logger.warning("AI provider %s lỗi, dùng template offline: %s", provider_info.name, exc)
            content = _offline_content(txn, stats, category_label)
            provider, model = "offline-fallback", "template-v1"
    else:
        content = _offline_content(txn, stats, category_label)

    latency_ms = int((time.perf_counter() - started) * 1000)
    explanation = Explanation(
        case_id=case.id,
        provider=provider,
        model=model,
        content=content,
        signals=signals,
        latency_ms=latency_ms,
        created_by=actor.id if actor else None,
    )
    db.add(explanation)
    db.flush()
    return explanation
