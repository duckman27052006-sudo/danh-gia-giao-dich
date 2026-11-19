from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="fraudlens-test-"))
# Mặc định test trên SQLite tạm cho nhanh. Đặt TEST_DATABASE_URL để chạy
# cùng một bộ test trên PostgreSQL (conftest sẽ drop & tạo lại schema, nên
# chỉ trỏ vào database dành riêng cho test, ví dụ fraudlens_test).
EXTERNAL_DB = os.environ.get("TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = EXTERNAL_DB or f"sqlite:///{(TEST_DIR / 'test.db').as_posix()}"
os.environ["SEED_ON_START"] = "false"
os.environ["AI_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-only-but-long-enough-32-chars"
os.environ["COOKIE_SECURE"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Setting, User  # noqa: E402
from app.seed import seed_merchants, seed_rules, seed_users  # noqa: E402


@pytest.fixture(scope="session")
def client():
    if EXTERNAL_DB:
        from app.db import Base, engine

        Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        if (db.scalar(select(func.count()).select_from(User)) or 0) == 0:
            db.add(Setting(id=1))
            seed_users(db)
            seed_merchants(db)
            seed_rules(db)
            db.commit()
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    return login(client, "admin@fraudlens.vn", "Admin@12345")


@pytest.fixture()
def analyst_headers(client: TestClient) -> dict[str, str]:
    return login(client, "analyst@fraudlens.vn", "Analyst@123")


@pytest.fixture()
def viewer_headers(client: TestClient) -> dict[str, str]:
    return login(client, "viewer@fraudlens.vn", "Viewer@123")
