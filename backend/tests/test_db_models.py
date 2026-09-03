from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import configure_mappers

from app import models  # noqa: F401
from app.db.base import Base

EXPECTED_TABLES = {
    "activation_attempts",
    "activations",
    "admin_sessions",
    "admin_users",
    "audit_logs",
    "customer_sessions",
    "customers",
    "email_otp_challenges",
    "packages",
    "payment_events",
    "router_package_profiles",
    "routers",
    "subscriptions",
    "transactions",
}


def _column_names(table_name: str) -> set[str]:
    return set(Base.metadata.tables[table_name].columns.keys())


def _foreign_key_targets(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {foreign_key.target_fullname for foreign_key in table.foreign_keys}


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    constraint_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    index_columns = {
        tuple(column.name for column in index.columns) for index in table.indexes if index.unique
    }
    return constraint_columns | index_columns


def test_redesigned_metadata_contains_all_system_boundaries() -> None:
    configure_mappers()
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_customer_schema_stores_only_a_pin_hash() -> None:
    customer_columns = _column_names("customers")

    assert "pin_hash" in customer_columns
    assert "pin" not in customer_columns
    assert "password" not in customer_columns
    assert {"router_id", "account_status", "email_verified_at"} <= customer_columns
    assert "routers.id" in _foreign_key_targets("customers")


def test_otp_and_session_secrets_are_stored_as_hashes() -> None:
    otp_columns = _column_names("email_otp_challenges")
    customer_session_columns = _column_names("customer_sessions")
    admin_session_columns = _column_names("admin_sessions")

    assert "code_hash" in otp_columns
    assert "code" not in otp_columns
    assert "token_hash" in customer_session_columns
    assert "token" not in customer_session_columns
    assert "token_hash" in admin_session_columns
    assert "token" not in admin_session_columns


def test_payment_and_activation_states_are_independent() -> None:
    transaction = Base.metadata.tables["transactions"]
    activation = Base.metadata.tables["activations"]

    assert "payment_status" in transaction.columns
    assert "activation_status" not in transaction.columns
    assert "status" in activation.columns
    assert set(transaction.c.payment_status.type.enums) == {"pending", "success", "failed"}
    assert {
        "not_started",
        "processing",
        "provisioning",
        "retry_required",
        "reconciliation_required",
        "success",
        "manual_review",
        "superseded",
    } == set(activation.c.status.type.enums)


def test_activation_records_a_retryable_target_and_ordered_router_receipt() -> None:
    activation_columns = _column_names("activations")

    assert {
        "activation_id",
        "sequence_number",
        "target_profile",
        "target_disabled",
        "attempt_count",
        "next_retry_at",
        "last_error_code",
        "last_error_message",
        "confirmed_at",
        "superseded_by_id",
    } <= activation_columns
    assert ("activation_id",) in _unique_column_sets("activations")
    assert ("sequence_number",) in _unique_column_sets("activations")
    assert ("transaction_id",) in _unique_column_sets("activations")


def test_activation_attempts_capture_read_before_write_evidence() -> None:
    attempt_columns = _column_names("activation_attempts")

    assert {
        "activation_id",
        "attempt_number",
        "trigger",
        "outcome",
        "observed_activation_id",
        "observed_profile",
        "observed_disabled",
        "router_state_before",
        "router_state_after",
        "error_code",
        "error_message",
    } <= attempt_columns
    assert ("activation_id", "attempt_number") in _unique_column_sets("activation_attempts")


def test_packages_map_to_router_specific_mikrotik_profiles() -> None:
    package_columns = _column_names("packages")
    mapping_columns = _column_names("router_package_profiles")

    assert {
        "amount",
        "currency",
        "duration_seconds",
        "data_limit_bytes",
        "device_limit",
        "is_active",
    } <= package_columns
    assert {"router_id", "package_id", "mikrotik_profile", "is_active"} <= (mapping_columns)
    assert ("router_id", "package_id") in _unique_column_sets("router_package_profiles")
    assert ("router_id", "mikrotik_profile") in _unique_column_sets("router_package_profiles")


def test_subscription_links_payment_activation_package_and_router() -> None:
    subscription_columns = _column_names("subscriptions")
    subscription_targets = _foreign_key_targets("subscriptions")

    assert {
        "customer_id",
        "package_id",
        "transaction_id",
        "activation_id",
        "router_id",
        "starts_at",
        "expires_at",
        "superseded_by_id",
    } <= subscription_columns
    assert {
        "customers.id",
        "packages.id",
        "transactions.id",
        "activations.id",
        "routers.id",
    } <= subscription_targets
    assert ("transaction_id",) in _unique_column_sets("subscriptions")
    assert ("activation_id",) in _unique_column_sets("subscriptions")


def test_webhook_idempotency_and_admin_auditing_have_durable_records() -> None:
    assert ("event_key",) in _unique_column_sets("payment_events")
    assert {"event_type", "status", "payload", "processed_at"} <= _column_names("payment_events")
    assert {
        "actor_type",
        "action",
        "entity_type",
        "entity_id",
        "details",
        "created_at",
    } <= _column_names("audit_logs")
