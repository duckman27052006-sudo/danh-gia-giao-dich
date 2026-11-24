"""Test cho chế độ đánh giá trên CSV gắn nhãn (`scripts/eval_model.py --csv`).

Mục đích: đảm bảo cùng một bộ chỉ số (PR-AUC, KS, Brier, calibration, ngưỡng) chạy
được trên dữ liệu thật mà không phải sửa script — và dữ liệu bẩn phải bị báo lỗi rõ
ràng thay vì bị lọc im lặng.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from app.features import FEATURE_NAMES, feature_vector
from app.ml.synthetic import generate_dataset
from scripts.eval_model import CONTEXT_COLUMNS, evaluate_csv, load_labeled_csv


@pytest.fixture(scope="module")
def records() -> list[dict]:
    return generate_dataset(seed=7, days=12, customers=40)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture(scope="module")
def feature_csv(tmp_path_factory: pytest.TempPathFactory, records: list[dict]) -> Path:
    rows = [
        {**dict(zip(FEATURE_NAMES, feature_vector(record), strict=True)), "label": int(record["label"])}
        for record in records
    ]
    path = tmp_path_factory.mktemp("eval") / "holdout_features.csv"
    return _write_csv(path, [*FEATURE_NAMES, "label"], rows)


@pytest.fixture(scope="module")
def context_csv(tmp_path_factory: pytest.TempPathFactory, records: list[dict]) -> Path:
    rows = [
        {**{name: record[name] for name in CONTEXT_COLUMNS}, "label": int(record["label"])}
        for record in records
    ]
    path = tmp_path_factory.mktemp("eval") / "holdout_context.csv"
    return _write_csv(path, [*CONTEXT_COLUMNS, "label"], rows)


def test_loads_feature_csv(feature_csv: Path, records: list[dict]) -> None:
    x, y, info = load_labeled_csv(feature_csv)
    assert x.shape == (len(records), len(FEATURE_NAMES))
    assert set(np.unique(y)) == {0, 1}
    assert info["input_mode"] == "features"
    assert info["label_column"] == "label"


def test_context_csv_produces_identical_features(context_csv: Path, feature_csv: Path) -> None:
    """Hai định dạng CSV phải cho ra cùng ma trận feature — nếu lệch là do parse."""
    x_context, y_context, info = load_labeled_csv(context_csv)
    x_features, y_features, _ = load_labeled_csv(feature_csv)
    assert info["input_mode"] == "context"
    assert np.array_equal(y_context, y_features)
    assert np.allclose(x_context, x_features, rtol=0, atol=1e-9)


def test_evaluate_csv_returns_full_metric_set(feature_csv: Path) -> None:
    report = evaluate_csv(feature_csv)
    assert report["source"] == "csv"
    assert report["input_mode"] == "features"
    assert report["roc_auc"] > 0.5
    assert 0.0 < report["average_precision"] <= 1.0
    assert 0.0 <= report["brier"] <= 1.0
    assert 0.0 <= report["ks"] <= 1.0
    assert report["thresholds"] and report["calibration"]
    assert report["test_size"] == len(load_labeled_csv(feature_csv)[1])


def test_custom_label_column(feature_csv: Path, tmp_path: Path) -> None:
    renamed = tmp_path / "renamed.csv"
    with feature_csv.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = [{("is_fraud" if key == "label" else key): value for key, value in row.items()} for row in reader]
    _write_csv(renamed, [*FEATURE_NAMES, "is_fraud"], rows)

    report = evaluate_csv(renamed, label_column="is_fraud")
    assert report["label_column"] == "is_fraud"
    assert report["roc_auc"] > 0.5


def test_missing_label_column_is_reported(feature_csv: Path, tmp_path: Path) -> None:
    path = tmp_path / "no_label.csv"
    _write_csv(path, list(FEATURE_NAMES), [dict.fromkeys(FEATURE_NAMES, 1.0)])
    with pytest.raises(ValueError, match="thiếu cột nhãn"):
        load_labeled_csv(path)


def test_incomplete_columns_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "partial.csv"
    _write_csv(path, ["amount", "label"], [{"amount": 1.0, "label": 0}])
    with pytest.raises(ValueError, match="13 cột feature"):
        load_labeled_csv(path)


def test_invalid_label_is_reported_with_row_number(feature_csv: Path, tmp_path: Path) -> None:
    path = tmp_path / "bad_label.csv"
    with feature_csv.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
    rows[0]["label"] = "khong_ro"
    _write_csv(path, [*FEATURE_NAMES, "label"], rows)
    with pytest.raises(ValueError, match="Dòng 2"):
        load_labeled_csv(path)


def test_single_class_dataset_is_rejected(feature_csv: Path, tmp_path: Path) -> None:
    path = tmp_path / "one_class.csv"
    with feature_csv.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    _write_csv(path, [*FEATURE_NAMES, "label"], [{**row, "label": 0} for row in rows])
    with pytest.raises(ValueError, match="một lớp nhãn"):
        load_labeled_csv(path)


def test_empty_dataset_is_rejected(feature_csv: Path, tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    _write_csv(path, [*FEATURE_NAMES, "label"], [])
    with pytest.raises(ValueError, match="không có dòng dữ liệu"):
        load_labeled_csv(path)
