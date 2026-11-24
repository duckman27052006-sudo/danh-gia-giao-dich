"""Đo tác động của cơ chế chấm điểm lên dữ liệu demo (chạy trên DB tạm, không đụng DB thật).

Script tạo lại toàn bộ dữ liệu demo bằng đúng pipeline hiện tại rồi in phân bố
case, để so sánh với snapshot demo đang có. Dùng để quyết định có nên sinh lại
dữ liệu demo hay không — chạy trên `fraudlens_test` (bộ test sẽ drop/recreate).

    $env:DATABASE_URL = "postgresql+psycopg://.../fraudlens_test"
    .\\.venv\\Scripts\\python.exe -m scripts.measure_demo_seed
"""

from __future__ import annotations

import os
import sys

# Phải đặt trước khi import app.* (settings đọc env lúc import).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://fraudlens:fraudlens_dev_password@127.0.0.1:5432/fraudlens_test",
)
os.environ["AI_ENABLED"] = "false"
os.environ["SEED_ON_START"] = "false"

if "test" not in os.environ["DATABASE_URL"].lower():
    raise SystemExit("Chỉ chạy trên database có tên chứa 'test'.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from sqlalchemy import func, select

    from app.db import Base, SessionLocal, engine, init_db
    from app.models import Case, Transaction
    from app.seed import seed_demo_data, seed_summary

    Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        seed_demo_data(db)
        summary = seed_summary(db)
        total = db.scalar(select(func.count()).select_from(Transaction)) or 0
        flagged = (
            db.scalar(
                select(func.count()).select_from(Transaction).where(Transaction.is_flagged.is_(True))
            )
            or 0
        )
        by_priority = db.execute(
            select(Case.priority, func.count()).group_by(Case.priority).order_by(Case.priority)
        ).all()
        by_band = db.execute(
            select(Transaction.risk_band, func.count())
            .group_by(Transaction.risk_band)
            .order_by(Transaction.risk_band)
        ).all()

    print("Tổng quan dữ liệu demo nếu sinh lại bằng pipeline hiện tại:")
    for key, value in summary.items():
        print(f"  {key:22} {value}")
    print(f"  {'alert_rate':22} {flagged / total:.2%} ({flagged}/{total})")
    print("  theo ưu tiên: " + ", ".join(f"{priority}={count}" for priority, count in by_priority))
    print("  theo risk band: " + ", ".join(f"{band}={count}" for band, count in by_band))


if __name__ == "__main__":
    main()
