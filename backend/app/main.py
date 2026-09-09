from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.dependencies import ROUTER_UNAVAILABLE_DETAIL
from app.routes import (
    account,
    admin_auth,
    admin_profiles,
    auth,
    health,
    hotspot,
    pages,
    payments,
    registration,
    routers,
    support,
)
from app.services.retention import delete_inactive_accounts

logger = logging.getLogger(__name__)

_PUBLIC_ERROR_DETAILS = {
    status.HTTP_400_BAD_REQUEST: "Invalid request.",
    status.HTTP_401_UNAUTHORIZED: "Invalid username or password.",
    status.HTTP_403_FORBIDDEN: "Access denied.",
    status.HTTP_404_NOT_FOUND: "The requested resource was not found.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Method not allowed.",
    status.HTTP_409_CONFLICT: "The request could not be completed.",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "Invalid request.",
    status.HTTP_423_LOCKED: "Account locked. Unlock it with an email verification code.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too many requests. Please try again later.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "An internal server error occurred.",
    status.HTTP_502_BAD_GATEWAY: ROUTER_UNAVAILABLE_DETAIL,
    status.HTTP_503_SERVICE_UNAVAILABLE: ROUTER_UNAVAILABLE_DETAIL,
    status.HTTP_504_GATEWAY_TIMEOUT: ROUTER_UNAVAILABLE_DETAIL,
}


def _public_error_detail(status_code: int) -> str:
    return _PUBLIC_ERROR_DETAILS.get(status_code, "Request failed.")


async def _retention_worker() -> None:
    settings = get_settings()
    # Let startup and migrations settle before the first pass.
    await asyncio.sleep(60)
    while True:
        try:
            deleted_count = await asyncio.to_thread(delete_inactive_accounts, settings)
            if deleted_count:
                logger.info("Deleted %s inactive customer account(s).", deleted_count)
        except Exception:
            logger.exception("Inactive account cleanup failed and will retry.")
        await asyncio.sleep(settings.inactive_account_cleanup_interval_seconds)


@asynccontextmanager
async def _lifespan(_application: FastAPI):
    settings = get_settings()
    retention_task = None
    if settings.inactive_account_cleanup_enabled:
        retention_task = asyncio.create_task(_retention_worker())
    try:
        yield
    finally:
        if retention_task is not None:
            retention_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await retention_task


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="MikroTik Hotspot API", version="0.3.0", lifespan=_lifespan
    )
    origins = settings.cors_origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(routers.router)
    application.include_router(hotspot.router)
    application.include_router(registration.router)
    application.include_router(auth.router)
    application.include_router(account.router)
    application.include_router(payments.router)
    application.include_router(admin_auth.router)
    application.include_router(admin_profiles.router)
    application.include_router(support.router)
    application.include_router(pages.router)

    @application.exception_handler(ServiceError)
    async def handle_service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _public_error_detail(exc.status_code)},
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _public_error_detail(exc.status_code)},
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": _public_error_detail(status.HTTP_422_UNPROCESSABLE_CONTENT)
            },
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_exception(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        # RouterOS exceptions can include login commands; never serialize exception text.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": _public_error_detail(status.HTTP_500_INTERNAL_SERVER_ERROR)
            },
        )

    return application


app = create_app()
