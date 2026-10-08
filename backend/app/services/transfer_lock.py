"""Hold one customer lock across journal commits, including across backend workers."""

import hashlib
import threading
from contextlib import contextmanager

from fastapi import status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ServiceError

_local_locks: dict[tuple[int, str], threading.Lock] = {}
_registry_lock = threading.Lock()


@contextmanager
def transfer_lock(session, customer_id):
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        key = int.from_bytes(
            hashlib.blake2b(f"hostel-transfer:{customer_id}".encode(), digest_size=8).digest(),
            "big",
            signed=True,
        )
        connection = bind.connect()
        acquired = False
        try:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            if not acquired:
                raise _busy()
            yield
        finally:
            try:
                if acquired:
                    connection.rollback()
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            except SQLAlchemyError:
                # Never return a pooled connection carrying a session-level lock.
                connection.invalidate()
            finally:
                connection.close()
    elif bind.dialect.name == "sqlite":
        # SQLite is a local test/development fallback, not cross-process locking.
        with _registry_lock:
            lock = _local_locks.setdefault((id(bind), str(customer_id)), threading.Lock())
        if not lock.acquire(blocking=False):
            raise _busy()
        try:
            yield
        finally:
            lock.release()
    else:
        raise RuntimeError("Transfer recovery requires PostgreSQL.")


def _busy():
    return ServiceError(
        status.HTTP_409_CONFLICT,
        "A hostel transfer is already running.",
        error_code="hostel_transfer_in_progress",
    )
