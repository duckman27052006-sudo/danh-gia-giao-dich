"""Nâng cấp schema PostgreSQL theo cách idempotent.

Project dùng ``Base.metadata.create_all`` cho database mới. Hàm
``apply_schema_migrations`` bổ sung phần còn thiếu cho các database đã tồn tại
từ phiên bản trước (JSON -> JSONB, khoá ngoại, CHECK constraint, index và
trigger audit bất biến). Hàm chạy lại nhiều lần không thay đổi kết quả.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, text

logger = logging.getLogger("fraudlens.schema")

JSON_COLUMNS: tuple[tuple[str, str], ...] = (
    ("transactions", "rule_hits"),
    ("transactions", "contributions"),
    ("case_events", "meta"),
    ("explanations", "content"),
    ("explanations", "signals"),
    ("rules", "conditions"),
    ("audit_logs", "before"),
    ("audit_logs", "after"),
)

# (table, constraint name, biểu thức CHECK)
CHECK_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("users", "ck_users_role", "role IN ('admin', 'analyst', 'viewer')"),
    ("merchants", "ck_merchants_risk_tier", "risk_tier IN ('low', 'medium', 'high')"),
    ("merchants", "ck_merchants_country", "char_length(country) = 2"),
    ("transactions", "ck_transactions_amount_positive", "amount > 0"),
    (
        "transactions",
        "ck_transactions_channel",
        "channel IN ('online', 'pos', 'atm', 'transfer')",
    ),
    (
        "transactions",
        "ck_transactions_risk_band",
        "risk_band IN ('low', 'medium', 'high', 'critical')",
    ),
    (
        "transactions",
        "ck_transactions_scores",
        "ml_score >= 0 AND ml_score <= 100 "
        "AND rule_score >= 0 AND rule_score <= 100 "
        "AND risk_score >= 0 AND risk_score <= 100",
    ),
    ("transactions", "ck_transactions_hour", "hour >= 0 AND hour <= 23"),
    (
        "transactions",
        "ck_transactions_velocity",
        "velocity_1h >= 0 AND velocity_24h >= 0",
    ),
    ("transactions", "ck_transactions_amount_ratio", "amount_ratio >= 0"),
    (
        "transactions",
        "ck_transactions_distinct_merchants",
        "distinct_merchants_24d >= 0",
    ),
    ("transactions", "ck_transactions_account_age", "account_age_days >= 0"),
    (
        "transactions",
        "ck_transactions_rule_hits_array",
        "jsonb_typeof(rule_hits) = 'array'",
    ),
    (
        "transactions",
        "ck_transactions_contributions_array",
        "jsonb_typeof(contributions) = 'array'",
    ),
    ("cases", "ck_cases_priority", "priority IN ('P1', 'P2', 'P3')"),
    (
        "cases",
        "ck_cases_status",
        "status IN ('open', 'in_review', 'awaiting_info', 'resolved')",
    ),
    (
        "cases",
        "ck_cases_decision",
        "decision IS NULL OR decision IN ('confirmed_fraud', 'false_positive', 'escalated')",
    ),
    ("cases", "ck_cases_risk_score", "risk_score >= 0 AND risk_score <= 100"),
    (
        "cases",
        "ck_cases_resolved_consistency",
        "status <> 'resolved' OR (decision IS NOT NULL AND resolved_at IS NOT NULL)",
    ),
    (
        "case_notes",
        "ck_case_notes_kind",
        "kind IN ('note', 'ai_draft', 'decision')",
    ),
    (
        "case_events",
        "ck_case_events_meta_object",
        "jsonb_typeof(meta) = 'object'",
    ),
    ("explanations", "ck_explanations_latency", "latency_ms >= 0"),
    (
        "explanations",
        "ck_explanations_content_object",
        "jsonb_typeof(content) = 'object'",
    ),
    (
        "explanations",
        "ck_explanations_signals_array",
        "jsonb_typeof(signals) = 'array'",
    ),
    ("rules", "ck_rules_weight", "weight >= 1 AND weight <= 100"),
    ("rules", "ck_rules_severity", "severity IN ('low', 'medium', 'high')"),
    ("rules", "ck_rules_hit_count", "hit_count >= 0"),
    (
        "rules",
        "ck_rules_conditions_array",
        "jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) > 0",
    ),
    ("settings", "ck_settings_singleton", "id = 1"),
    (
        "settings",
        "ck_settings_thresholds",
        "review_threshold >= 0 AND review_threshold <= 100 "
        "AND high_threshold >= 0 AND high_threshold <= 100 "
        "AND high_threshold > review_threshold",
    ),
    (
        "settings",
        "ck_settings_weights",
        "ml_weight >= 0 AND ml_weight <= 1 "
        "AND rule_weight >= 0 AND rule_weight <= 1 "
        "AND (ml_weight + rule_weight) > 0",
    ),
    (
        "settings",
        "ck_settings_flag_gates",
        "ml_flag_probability >= 0 AND ml_flag_probability <= 1 "
        "AND rule_flag_threshold >= 0 AND rule_flag_threshold <= 100",
    ),
)

# (table, column, referenced table, ON DELETE action, constraint name)
FK_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    ("cases", "transaction_id", "transactions", "CASCADE", "fk_cases_transaction"),
    ("cases", "assigned_to", "users", "SET NULL", "fk_cases_assigned_to"),
    ("case_notes", "case_id", "cases", "CASCADE", "fk_case_notes_case"),
    ("case_notes", "author_id", "users", "SET NULL", "fk_case_notes_author"),
    ("case_events", "case_id", "cases", "CASCADE", "fk_case_events_case"),
    ("case_events", "actor_id", "users", "SET NULL", "fk_case_events_actor"),
    ("explanations", "case_id", "cases", "CASCADE", "fk_explanations_case"),
    ("explanations", "created_by", "users", "SET NULL", "fk_explanations_created_by"),
    ("refresh_sessions", "user_id", "users", "CASCADE", "fk_refresh_sessions_user"),
    ("transactions", "merchant_id", "merchants", "SET NULL", "fk_transactions_merchant"),
)

DELETE_ACTION_CODES = {"CASCADE": "c", "SET NULL": "n", "NO ACTION": "a", "RESTRICT": "r"}

# Index cũ bị thay bằng composite/partial index cùng mục đích.
LEGACY_INDEXES: tuple[str, ...] = (
    "ix_transactions_customer_id",
    "ix_transactions_is_flagged",
    "ix_transactions_risk_band",
    "ix_transactions_flagged_occurred",
    "ix_cases_status",
    "ix_cases_priority",
    "ix_case_notes_case_id",
    "ix_case_events_case_id",
    "ix_explanations_case_id",
    "ix_audit_logs_action",
    "ix_audit_logs_entity_type",
    "ix_audit_logs_actor_id",
)

INDEX_DDL: tuple[tuple[str, str], ...] = (
    (
        "ix_transactions_customer_occurred",
        "CREATE INDEX IF NOT EXISTS ix_transactions_customer_occurred "
        "ON public.transactions USING btree (customer_id, occurred_at)",
    ),
    (
        "ix_transactions_risk_band_occurred",
        "CREATE INDEX IF NOT EXISTS ix_transactions_risk_band_occurred "
        "ON public.transactions USING btree (risk_band, occurred_at)",
    ),
    (
        "ix_transactions_channel_occurred",
        "CREATE INDEX IF NOT EXISTS ix_transactions_channel_occurred "
        "ON public.transactions USING btree (channel, occurred_at)",
    ),
    (
        "ix_transactions_flagged_recent",
        "CREATE INDEX IF NOT EXISTS ix_transactions_flagged_recent "
        "ON public.transactions USING btree (occurred_at) WHERE is_flagged",
    ),
    (
        "ix_transactions_merchant_id",
        "CREATE INDEX IF NOT EXISTS ix_transactions_merchant_id "
        "ON public.transactions USING btree (merchant_id)",
    ),
    (
        "ix_cases_status_sla",
        "CREATE INDEX IF NOT EXISTS ix_cases_status_sla "
        "ON public.cases USING btree (status, sla_due_at)",
    ),
    (
        "ix_cases_created_at",
        "CREATE INDEX IF NOT EXISTS ix_cases_created_at "
        "ON public.cases USING btree (created_at)",
    ),
    (
        "ix_cases_open_priority",
        "CREATE INDEX IF NOT EXISTS ix_cases_open_priority "
        "ON public.cases USING btree (priority) WHERE status <> 'resolved'",
    ),
    (
        "ix_case_notes_case_created",
        "CREATE INDEX IF NOT EXISTS ix_case_notes_case_created "
        "ON public.case_notes USING btree (case_id, created_at)",
    ),
    (
        "ix_case_notes_author_id",
        "CREATE INDEX IF NOT EXISTS ix_case_notes_author_id "
        "ON public.case_notes USING btree (author_id)",
    ),
    (
        "ix_case_events_case_created",
        "CREATE INDEX IF NOT EXISTS ix_case_events_case_created "
        "ON public.case_events USING btree (case_id, created_at)",
    ),
    (
        "ix_case_events_actor_id",
        "CREATE INDEX IF NOT EXISTS ix_case_events_actor_id "
        "ON public.case_events USING btree (actor_id)",
    ),
    (
        "ix_explanations_case_created",
        "CREATE INDEX IF NOT EXISTS ix_explanations_case_created "
        "ON public.explanations USING btree (case_id, created_at)",
    ),
    (
        "ix_explanations_created_by",
        "CREATE INDEX IF NOT EXISTS ix_explanations_created_by "
        "ON public.explanations USING btree (created_by)",
    ),
    (
        "ix_audit_logs_action_created",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_action_created "
        "ON public.audit_logs USING btree (action, created_at)",
    ),
    (
        "ix_audit_logs_entity_created",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_created "
        "ON public.audit_logs USING btree (entity_type, created_at)",
    ),
    (
        "ix_audit_logs_actor_created",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_created "
        "ON public.audit_logs USING btree (actor_id, created_at)",
    ),
    (
        "ux_users_email_lower",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_lower "
        "ON public.users USING btree (lower(email))",
    ),
    (
        "ux_merchants_name_lower",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_merchants_name_lower "
        "ON public.merchants USING btree (lower(name))",
    ),
)


def _table_exists(conn, table: str) -> bool:  # type: ignore[no-untyped-def]
    return bool(conn.scalar(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}))


def _upgrade_json_columns(conn) -> None:  # type: ignore[no-untyped-def]
    for table, column in JSON_COLUMNS:
        data_type = conn.scalar(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        )
        if data_type == "json":
            conn.execute(
                text(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
                    f'TYPE jsonb USING "{column}"::jsonb'
                )
            )
            logger.info("Đã chuyển %s.%s sang jsonb", table, column)


def _ensure_merchant_column(conn) -> None:  # type: ignore[no-untyped-def]
    conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_id varchar(32)"))
    # Backfill theo tên merchant; dữ liệu cũ không phân biệt hoa/thường.
    conn.execute(
        text(
            "UPDATE transactions AS t SET merchant_id = m.id "
            "FROM merchants AS m "
            "WHERE t.merchant_id IS NULL AND lower(t.merchant_name) = lower(m.name)"
        )
    )


def _ensure_settings_columns(conn) -> None:  # type: ignore[no-untyped-def]
    """Thêm cột ngưỡng thành phần cho database tạo từ phiên bản trước."""
    conn.execute(
        text(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS "
            "ml_flag_probability double precision NOT NULL DEFAULT 0.65"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS "
            "rule_flag_threshold double precision NOT NULL DEFAULT 80.0"
        )
    )


def _ensure_foreign_keys(conn) -> None:  # type: ignore[no-untyped-def]
    for table, column, ref_table, on_delete, name in FK_SPECS:
        existing = conn.execute(
            text(
                "SELECT c.conname, c.confdeltype "
                "FROM pg_constraint AS c "
                "JOIN pg_attribute AS a "
                "  ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
                "WHERE c.contype = 'f' "
                "  AND c.conrelid = to_regclass(:table) "
                "  AND a.attname = :column "
                "  AND cardinality(c.conkey) = 1"
            ),
            {"table": f"public.{table}", "column": column},
        ).all()

        desired_code = DELETE_ACTION_CODES[on_delete]
        for conname, action_code in existing:
            if conname != name or action_code != desired_code:
                conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{conname}"'))

        still_exists = conn.scalar(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = :name AND conrelid = to_regclass(:table)"
            ),
            {"name": name, "table": f"public.{table}"},
        )
        if still_exists:
            continue

        conn.execute(
            text(
                f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
                f'FOREIGN KEY ("{column}") REFERENCES "{ref_table}" (id) '
                f"ON DELETE {on_delete} NOT VALID"
            )
        )
        conn.execute(text(f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"'))


def _ensure_check_constraints(conn) -> None:  # type: ignore[no-untyped-def]
    for table, name, expression in CHECK_CONSTRAINTS:
        row = conn.execute(
            text(
                "SELECT convalidated FROM pg_constraint "
                "WHERE conname = :name AND conrelid = to_regclass(:table)"
            ),
            {"name": name, "table": f"public.{table}"},
        ).first()
        if row is None:
            conn.execute(
                text(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
                    f"CHECK ({expression}) NOT VALID"
                )
            )
            conn.execute(text(f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"'))
            logger.info("Đã thêm CHECK %s", name)
        elif not row[0]:
            conn.execute(text(f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"'))


def _rebuild_indexes(conn) -> None:  # type: ignore[no-untyped-def]
    for name in LEGACY_INDEXES:
        conn.execute(text(f'DROP INDEX IF EXISTS public."{name}"'))
    for _name, ddl in INDEX_DDL:
        conn.execute(text(ddl))


def _ensure_audit_immutability(conn) -> None:  # type: ignore[no-untyped-def]
    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION fraudlens_block_audit_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'audit_logs là bảng append-only, không được sửa hoặc xoá';
            END;
            $$;
            """
        )
    )
    trigger_exists = conn.scalar(
        text(
            "SELECT 1 FROM pg_trigger "
            "WHERE tgname = 'trg_audit_logs_immutable' "
            "AND tgrelid = to_regclass('public.audit_logs')"
        )
    )
    if not trigger_exists:
        conn.execute(
            text(
                "CREATE TRIGGER trg_audit_logs_immutable "
                "BEFORE UPDATE OR DELETE ON audit_logs "
                "FOR EACH ROW EXECUTE FUNCTION fraudlens_block_audit_mutation()"
            )
        )


def apply_schema_migrations(engine: Engine) -> None:
    """Áp dụng nâng cấp schema; an toàn khi gọi lặp lại sau ``create_all``."""
    if engine.dialect.name != "postgresql":
        return
    with engine.connect() as probe:
        has_tables = _table_exists(probe, "transactions")
    if not has_tables:
        return

    with engine.begin() as conn:
        _upgrade_json_columns(conn)
        _ensure_merchant_column(conn)
        _ensure_settings_columns(conn)
        _ensure_foreign_keys(conn)
        _ensure_check_constraints(conn)
        _rebuild_indexes(conn)
        _ensure_audit_immutability(conn)
    logger.debug("Schema migrations đã được áp dụng")
