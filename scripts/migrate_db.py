"""Áp dụng nâng cấp schema cho database hiện tại.

App cũng tự chạy bước này trong ``init_db()`` khi khởi động; script dùng khi
muốn migrate thủ công trước khi bật app.

Chạy: ``python scripts/migrate_db.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.db import engine, init_db

    init_db()
    print(f"Schema updated: {engine.url.render_as_string(hide_password=True)}")


if __name__ == "__main__":
    main()
