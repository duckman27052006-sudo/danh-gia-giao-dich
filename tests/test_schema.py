from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, engine
from app.models import Merchant, User
from app.schemas import TransactionIn
from app.scoring import ingest_transaction


def test_json_columns_use_jsonb(client: TestClient) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name || '.' || column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type IN ('json', 'jsonb')"
            )
        ).all()
    types = {row[1] for row in rows}
    assert rows
    assert types == {"jsonb"}


def test_constraints_and_audit_trigger_installed(client: TestClient) -> None:
    expected_checks = {
        "ck_users_role",
        "ck_transactions_amount_positive",
        "ck_transactions_scores",
        "ck_cases_resolved_consistency",
        "ck_rules_conditions_array",
        "ck_settings_thresholds",
    }
    with engine.connect() as conn:
        checks = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE connamespace = 'public'::regnamespace AND contype = 'c'"
                )
            )
        }
        merchant_fk = conn.scalar(
            text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conname = 'fk_transactions_merchant'"
            )
        )
        trigger = conn.scalar(
            text(
                "SELECT 1 FROM pg_trigger "
                "WHERE tgname = 'trg_audit_logs_immutable' "
                "AND tgrelid = to_regclass('public.audit_logs')"
            )
        )
    assert expected_checks <= checks
    assert merchant_fk == "n"  # ON DELETE SET NULL
    assert trigger == 1


def test_invalid_role_is_rejected(client: TestClient) -> None:
    with SessionLocal() as db:
        db.add(
            User(
                email=f"bad-role-{uuid.uuid4().hex[:8]}@test.local",
                full_name="Bad Role",
                password_hash="x",
                role="owner",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_ingest_creates_and_links_merchant(client: TestClient) -> None:
    name = f"Merchant Test {uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        txn = ingest_transaction(
            db,
            TransactionIn(
                external_id=f"TEST-{uuid.uuid4().hex[:12]}",
                customer_id=f"CUS-{uuid.uuid4().hex[:8]}",
                amount=123_456,
                merchant_name=name,
                merchant_category="crypto",
                merchant_country="SC",
            ),
        )
        assert txn.merchant_id is not None
        merchant = db.get(Merchant, txn.merchant_id)
        assert merchant is not None
        assert merchant.name == name
        assert merchant.risk_tier == "high"
