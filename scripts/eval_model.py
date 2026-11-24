"""Đánh giá model đã huấn luyện trên tập test và in bảng operating point.

Script chỉ ĐỌC: dựng lại dataset tổng hợp theo đúng seed/tham số của artifact
(xem ``metadata.json``), chia train/test theo thời gian giống ``app/ml/train.py``,
nạp ``model.joblib`` và tính các chỉ số phục vụ quyết định ngưỡng vận hành:

- ROC-AUC, PR-AUC (average precision), KS, Brier
- Bảng calibration theo bin
- Precision / recall / F1 / FPR tại từng ngưỡng xác suất

Dùng để chọn ``ML_FLAG_PROBABILITY`` trong bảng ``settings`` và để cập nhật
``docs/model-card.md`` bằng số đo thật.

    .\\.venv\\Scripts\\python.exe -m scripts.eval_model
    .\\.venv\\Scripts\\python.exe -m scripts.eval_model --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

from app.features import FEATURE_NAMES, feature_vector
from app.ml.service import load_artifact, metadata
from app.ml.synthetic import generate_dataset

THRESHOLD_GRID = (0.30, 0.40, 0.50, 0.55, 0.60, 0.62, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


def _test_split() -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Tái lập đúng cách chia của train_and_save: sort theo thời gian, 80/20."""
    dataset = metadata().get("dataset", {})
    records = generate_dataset(
        seed=int(dataset.get("seed", 42)),
        days=int(dataset.get("days", 60)),
        customers=int(dataset.get("customers", 900)),
    )
    x = np.array([feature_vector(record) for record in records], dtype=float)
    y = np.array([int(record["label"]) for record in records])
    timestamps = np.array([record["occurred_at"] for record in records])
    order = np.argsort(timestamps)
    x, y = x[order], y[order]
    split = int(len(x) * 0.8)
    return x[split:], y[split:], [records[index] for index in order[split:]]


def _ks_statistic(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    """Khoảng cách lớn nhất giữa CDF của lớp dương và lớp âm."""
    order = np.argsort(probabilities)
    y_sorted = y_true[order]
    positives = max(int(y_sorted.sum()), 1)
    negatives = max(int(len(y_sorted) - y_sorted.sum()), 1)
    cdf_pos = np.cumsum(y_sorted) / positives
    cdf_neg = np.cumsum(1 - y_sorted) / negatives
    return float(np.max(np.abs(cdf_pos - cdf_neg)))


def _confusion(y_true: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict[str, float]:
    predicted = probabilities >= threshold
    tp = int(np.sum(predicted & (y_true == 1)))
    fp = int(np.sum(predicted & (y_true == 0)))
    fn = int(np.sum(~predicted & (y_true == 1)))
    tn = int(np.sum(~predicted & (y_true == 0)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {
        "threshold": round(float(threshold), 2),
        "flagged_rate": round(float(predicted.mean()), 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fpr": round(fpr, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def _calibration(y_true: np.ndarray, probabilities: np.ndarray, bins: int = 5) -> list[dict[str, Any]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, Any]] = []
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        mask = (probabilities >= low) & (probabilities < high if index < bins - 1 else probabilities <= high)
        if not mask.any():
            continue
        rows.append(
            {
                "bin": f"{low:.2f}-{high:.2f}",
                "count": int(mask.sum()),
                "mean_predicted": round(float(probabilities[mask].mean()), 4),
                "observed": round(float(y_true[mask].mean()), 4),
            }
        )
    return rows


def rule_gate_report(
    probabilities: np.ndarray,
    y_test: np.ndarray,
    records: list[dict[str, Any]],
    ml_gate: float,
    rule_gate: float,
    blend_weight: tuple[float, float] = (0.55, 0.45),
    review_threshold: float = 55.0,
) -> dict[str, Any]:
    """So sánh cơ chế gắn cờ cũ (chỉ blend) với cơ chế 2 ngưỡng OR.

    ``record`` từ dataset tổng hợp có đủ field mà rule engine dùng, nên có thể
    chấm ``rule_score`` y hệt lúc serving. Cần database có bảng ``rules``.
    """
    from app.db import SessionLocal
    from app.rules import evaluate_rules, load_enabled_rules

    with SessionLocal() as db:
        rules = load_enabled_rules(db)
    if not rules:
        return {"error": "Không có rule nào đang bật trong database — bỏ qua phân tích rule."}

    rule_scores = np.array([evaluate_rules(rules, record)[0] for record in records], dtype=float)
    ml_scores = probabilities * 100
    ml_w, rule_w = blend_weight
    blends = ml_scores * ml_w + rule_scores * rule_w

    old_flagged = blends >= review_threshold
    new_flagged = old_flagged | (probabilities >= ml_gate) | (rule_scores >= rule_gate)

    def summary(mask: np.ndarray) -> dict[str, Any]:
        tp = int(np.sum(mask & (y_test == 1)))
        fp = int(np.sum(mask & (y_test == 0)))
        fn = int(np.sum(~mask & (y_test == 1)))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        return {
            "flagged": int(mask.sum()),
            "flagged_rate": round(float(mask.mean()), 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    recovered = new_flagged & ~old_flagged
    return {
        "rules_enabled": len(rules),
        "ml_gate": ml_gate,
        "rule_gate": rule_gate,
        "blend_only": summary(old_flagged),
        "two_gate": summary(new_flagged),
        "newly_flagged": {
            **summary(recovered),
            "recovered_fraud": int(np.sum(recovered & (y_test == 1))),
        },
        "rule_score_percentiles": {
            label: round(float(np.percentile(rule_scores, q)), 1)
            for label, q in (("p50", 50), ("p90", 90), ("p99", 99))
        },
    }


def _metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    """Bộ chỉ số dùng chung cho cả dữ liệu tổng hợp và dữ liệu gắn nhãn thật."""
    return {
        "test_size": len(y_true),
        "test_fraud": int(y_true.sum()),
        "fraud_rate": round(float(y_true.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 4),
        "average_precision": round(float(average_precision_score(y_true, probabilities)), 4),
        "ks": round(_ks_statistic(y_true, probabilities), 4),
        "brier": round(float(brier_score_loss(y_true, probabilities)), 4),
        "mean_predicted": round(float(probabilities.mean()), 4),
        "thresholds": [_confusion(y_true, probabilities, t) for t in THRESHOLD_GRID],
        "calibration": _calibration(y_true, probabilities),
        "feature_names": FEATURE_NAMES,
    }


# Hai định dạng CSV được chấp nhận: hoặc 13 cột feature đã tính sẵn, hoặc các cột
# context thô mà `feature_vector` cần. Nhờ vậy có thể đánh giá trực tiếp bằng file
# export từ kho dữ liệu thật mà không phải viết lại script.
CONTEXT_COLUMNS: tuple[str, ...] = (
    "amount",
    "hour",
    "is_night",
    "country_mismatch",
    "new_device",
    "velocity_1h",
    "velocity_24h",
    "amount_ratio",
    "distinct_merchants_24d",
    "account_age_days",
    "merchant_category",
    "channel",
)
NUMERIC_CONTEXT_COLUMNS = (
    "amount",
    "hour",
    "velocity_1h",
    "velocity_24h",
    "amount_ratio",
    "distinct_merchants_24d",
    "account_age_days",
)
TRUE_TOKENS = {"1", "1.0", "true", "yes", "y", "t", "fraud"}
FALSE_TOKENS = {"0", "0.0", "false", "no", "n", "f", "legit", "normal"}


def _parse_label(raw: str | None, row_number: int, column: str) -> int:
    token = (raw or "").strip().lower()
    if token in TRUE_TOKENS:
        return 1
    if token in FALSE_TOKENS:
        return 0
    raise ValueError(
        f"Dòng {row_number}: cột nhãn {column!r} có giá trị {raw!r} không hợp lệ "
        f"(chấp nhận 0/1, true/false, yes/no, fraud/legit)."
    )


def _parse_bool(raw: str | None, row_number: int, column: str) -> bool:
    token = (raw or "").strip().lower()
    if token in TRUE_TOKENS:
        return True
    if token in FALSE_TOKENS:
        return False
    raise ValueError(f"Dòng {row_number}: cột {column!r} phải là 0/1 hoặc true/false, nhận được {raw!r}.")


def _parse_float(raw: str | None, row_number: int, column: str) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Dòng {row_number}: cột {column!r} không phải số (nhận được {raw!r}).") from exc


def load_labeled_csv(path: str | Path, label_column: str = "label") -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Đọc CSV gắn nhãn và trả về ``(X, y, thông tin nguồn)``.

    File phải có cột nhãn (mặc định ``label``) và **một trong hai** bộ cột:
    13 feature đã tính sẵn, hoặc các cột context thô. Không âm thầm bỏ qua dòng lỗi:
    dữ liệu bẩn phải được báo rõ số dòng để sửa, vì một báo cáo hiệu năng tính
    trên dữ liệu lọc ngầm thì không dùng được.
    """
    import csv

    csv_path = Path(path)
    if not csv_path.exists():
        raise ValueError(f"Không tìm thấy file CSV: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if label_column not in fieldnames:
            raise ValueError(
                f"CSV thiếu cột nhãn {label_column!r}. Các cột hiện có: {', '.join(fieldnames) or '(trống)'}"
            )
        feature_mode = all(name in fieldnames for name in FEATURE_NAMES)
        context_mode = all(name in fieldnames for name in CONTEXT_COLUMNS)
        if not feature_mode and not context_mode:
            missing = [name for name in CONTEXT_COLUMNS if name not in fieldnames]
            raise ValueError(
                "CSV phải có đủ 13 cột feature "
                f"({', '.join(FEATURE_NAMES)}) hoặc đủ các cột context ({', '.join(CONTEXT_COLUMNS)}). "
                f"Cột còn thiếu nếu đi theo dạng context: {', '.join(missing)}"
            )

        rows: list[list[float]] = []
        labels: list[int] = []
        for row_number, row in enumerate(reader, start=2):  # dòng 1 là header
            if feature_mode:
                rows.append(
                    [_parse_float(row.get(name), row_number, name) for name in FEATURE_NAMES]
                )
            else:
                ctx: dict[str, Any] = {
                    name: _parse_float(row.get(name), row_number, name)
                    for name in NUMERIC_CONTEXT_COLUMNS
                }
                ctx["hour"] = int(ctx["hour"])
                for name in ("is_night", "country_mismatch", "new_device"):
                    ctx[name] = _parse_bool(row.get(name), row_number, name)
                ctx["merchant_category"] = (row.get("merchant_category") or "other").strip()
                ctx["channel"] = (row.get("channel") or "pos").strip()
                rows.append(feature_vector(ctx))
            labels.append(_parse_label(row.get(label_column), row_number, label_column))

    if not rows:
        raise ValueError(f"CSV không có dòng dữ liệu nào: {csv_path}")

    y = np.array(labels, dtype=int)
    if len(set(labels)) < 2:
        raise ValueError(
            "CSV chỉ có một lớp nhãn — không tính được ROC-AUC/PR-AUC. "
            "Cần cả giao dịch gian lận và hợp lệ trong file."
        )

    info = {
        "csv_path": str(csv_path),
        "input_mode": "features" if feature_mode else "context",
        "label_column": label_column,
    }
    return np.array(rows, dtype=float), y, info


def evaluate(
    *,
    with_rules: bool = False,
    ml_gate: float = 0.65,
    rule_gate: float = 80.0,
) -> dict[str, Any]:
    """Đánh giá trên tập test dựng lại từ dataset tổng hợp của artifact."""
    x_test, y_test, records = _test_split()
    model = load_artifact()["model"]
    probabilities = model.predict_proba(x_test)[:, 1]

    report = {
        "source": "synthetic",
        "model_version": metadata()["version"],
        "dataset": metadata().get("dataset", {}),
        **_metrics(y_test, probabilities),
    }
    if with_rules:
        report["rule_gate"] = rule_gate_report(probabilities, y_test, records, ml_gate, rule_gate)
    return report


def evaluate_csv(
    path: str | Path,
    *,
    label_column: str = "label",
) -> dict[str, Any]:
    """Đánh giá trên file CSV gắn nhãn (dữ liệu thật hoặc tập holdout tự chuẩn bị)."""
    x, y, info = load_labeled_csv(path, label_column)
    model = load_artifact()["model"]
    probabilities = model.predict_proba(x)[:, 1]
    return {
        "source": "csv",
        "model_version": metadata()["version"],
        **info,
        **_metrics(y, probabilities),
    }


def _print_report(report: dict[str, Any]) -> None:
    if report.get("source") == "csv":
        print(
            f"Nguồn: {report.get('csv_path')} ({report['input_mode']} mode, cột nhãn "
            f"{report['label_column']!r}) — chỉ số chỉ có nghĩa nếu nhãn được xác minh độc lập."
        )
    else:
        dataset = report.get("dataset", {})
        print(
            "Nguồn: dataset tổng hợp của artifact "
            f"(seed={dataset.get('seed')}, days={dataset.get('days')}, customers={dataset.get('customers')}) "
            "— benchmark đường ống, KHÔNG phải năng lực phát hiện trên dữ liệu thật."
        )
    print(f"Model {report['model_version']} · test {report['test_size']} dòng · "
          f"{report['test_fraud']} fraud ({report['fraud_rate']:.1%})")
    print(f"ROC-AUC {report['roc_auc']:.4f} · PR-AUC {report['average_precision']:.4f} · "
          f"KS {report['ks']:.4f} · Brier {report['brier']:.4f} · "
          f"p dự báo TB {report['mean_predicted']:.4f}")
    print()
    print("| Ngưỡng p | Tỷ lệ gắn cờ | Precision | Recall | F1 | FPR | TP | FP | FN |")
    print("|---|---|---|---|---|---|---|---|---|")
    for row in report["thresholds"]:
        print(
            f"| {row['threshold']:.2f} | {row['flagged_rate']:.1%} | {row['precision']:.3f} | "
            f"{row['recall']:.3f} | {row['f1']:.3f} | {row['fpr']:.2%} | {row['tp']} | {row['fp']} | {row['fn']} |"
        )
    print()
    print("| Bin xác suất | Số dòng | p dự báo TB | Tỷ lệ fraud thật |")
    print("|---|---|---|---|")
    for row in report["calibration"]:
        print(f"| {row['bin']} | {row['count']} | {row['mean_predicted']:.3f} | {row['observed']:.3f} |")

    rule_gate = report.get("rule_gate")
    if rule_gate:
        if "error" in rule_gate:
            print()
            print(rule_gate["error"])
            return
        print()
        print(
            f"Cơ chế gắn cờ (ML gate p≥{rule_gate['ml_gate']:.2f}, "
            f"rule gate ≥{rule_gate['rule_gate']:.0f} điểm, {rule_gate['rules_enabled']} rule đang bật):"
        )
        print("| Cơ chế | Số case | Tỷ lệ | Precision | Recall | TP | FP | FN |")
        print("|---|---|---|---|---|---|---|---|")
        for label, key in (("Chỉ blend (hiện tại)", "blend_only"), ("Hai ngưỡng OR (đề xuất)", "two_gate")):
            row = rule_gate[key]
            print(
                f"| {label} | {row['flagged']} | {row['flagged_rate']:.1%} | {row['precision']:.3f} | "
                f"{row['recall']:.3f} | {row['tp']} | {row['fp']} | {row['fn']} |"
            )
        newly = rule_gate["newly_flagged"]
        print()
        print(
            f"Case được cứu thêm: {newly['flagged']} (trong đó {newly['recovered_fraud']} fraud thật, "
            f"{newly['fp']} báo nhầm). "
            f"rule_score p50/p90/p99 = {rule_gate['rule_score_percentiles']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Đánh giá model FraudLens và in bảng ngưỡng vận hành. Mặc định chạy trên dataset "
            "tổng hợp của artifact; dùng --csv để đánh giá trên file gắn nhãn thật."
        )
    )
    parser.add_argument("--json", action="store_true", help="in JSON thay vì bảng markdown")
    parser.add_argument(
        "--csv",
        metavar="PATH",
        help=(
            "đánh giá trên CSV gắn nhãn: cần cột nhãn và đủ 13 cột feature, "
            "hoặc đủ các cột context thô"
        ),
    )
    parser.add_argument(
        "--label-column",
        default="label",
        help="tên cột nhãn trong CSV (mặc định: label)",
    )
    parser.add_argument(
        "--with-rules",
        action="store_true",
        help="chấm thêm rule_score từ database để so sánh cơ chế gắn cờ cũ/mới (chỉ dùng với dataset tổng hợp)",
    )
    parser.add_argument("--ml-gate", type=float, default=0.65, help="ngưỡng xác suất ML để tự gắn cờ")
    parser.add_argument("--rule-gate", type=float, default=80.0, help="ngưỡng điểm rule để tự gắn cờ")
    args = parser.parse_args()
    # Console Windows mặc định cp1252 → in tiếng Việt sẽ lỗi UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.csv and args.with_rules:
        parser.error("--with-rules cần context gốc + database rule, không dùng chung với --csv")

    try:
        if args.csv:
            report = evaluate_csv(args.csv, label_column=args.label_column)
        else:
            report = evaluate(
                with_rules=args.with_rules, ml_gate=args.ml_gate, rule_gate=args.rule_gate
            )
    except ValueError as exc:
        parser.exit(2, f"Lỗi dữ liệu: {exc}\n")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)


if __name__ == "__main__":
    main()
