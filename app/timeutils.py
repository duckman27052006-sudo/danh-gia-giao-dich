"""Tiện ích thời gian dùng chung cho toàn bộ ứng dụng.

Database lưu mọi mốc thời gian dưới dạng UTC *naive* (xem ``UTCDateTime`` trong
``app/models.py``). Vì vậy mọi giá trị ``datetime`` đi vào truy vấn phải được
chuẩn hoá qua :func:`to_naive_utc` thay vì ``.replace(tzinfo=None)`` — cách sau
chỉ *bỏ* offset chứ không *đổi* sang UTC, làm lệch giờ khi client gửi offset
khác 0 (ví dụ ``2026-01-01T00:00+07:00``).
"""

from __future__ import annotations

from datetime import datetime, timezone


def to_naive_utc(value: datetime) -> datetime:
    """Đổi ``datetime`` (aware hoặc naive) về UTC naive để so sánh với cột DB."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
