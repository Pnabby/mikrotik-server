"""Check authenticated APIs rather than cached router status or a ping."""

import logging

from routeros_api.exceptions import RouterOsApiConnectionError, RouterOsApiError

from app.core.exceptions import ServiceError
from app.integrations.mikrotik.registry import UnknownRouterError, get_router

logger = logging.getLogger(__name__)


def router_failure_reason(exc):
    if isinstance(exc, (OSError, RouterOsApiConnectionError)):
        return "unreachable"
    # Inspect errors only to select fixed codes. Raw API messages can contain
    # credentials/scripts and must never reach responses or logs.
    message = str(exc).lower()
    if any(
        text in message
        for text in (
            "cannot log in",
            "invalid user name or password",
            "login failed",
            "not logged in",
        )
    ):
        return "authentication_failed"
    if any(
        text in message for text in ("not enough permissions", "permission denied", "not permitted")
    ):
        return "permission_denied"
    if any(
        text in message
        for text in ("unknown command", "no such command", "bad command name", "unknown parameter")
    ):
        return "commands_unavailable"
    return "request_failed"


def transfer_router_read(side, read):
    """Only used before the durable transfer intent and any account mutations."""
    try:
        return read()
    except (OSError, RouterOsApiError) as exc:
        code = f"hostel_{side}_router_{router_failure_reason(exc)}"
        logger.warning("Hostel transfer preflight failed: reason=%s", code)
        raise ServiceError(503, "Router API preflight failed.", error_code=code) from None


def check_transfer_routers(source, destination):
    failures = {}
    for side, client in (("source", source), ("destination", destination)):
        try:
            transfer_router_read(side, client.check_transfer_availability)
        except ServiceError as exc:
            failures[side] = exc
    # Always check both sides, even if the first connection fails.
    if len(failures) == 2:
        raise ServiceError(
            503,
            "Neither router API is ready for transfer.",
            error_code="hostel_both_routers_not_ready",
            field_errors={side: failure.error_code for side, failure in failures.items()},
        )
    if failures:
        raise next(iter(failures.values()))


def resolve_transfer_routers(session, source_id, destination_id):
    routers = []
    for side, router_id in (("source", source_id), ("destination", destination_id)):
        try:
            routers.append(get_router(session, router_id))
        except UnknownRouterError:
            raise ServiceError(
                503,
                "Router catalogue configuration is missing.",
                error_code=f"hostel_{side}_router_not_configured",
            ) from None
    return tuple(routers)
