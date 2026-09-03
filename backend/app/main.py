from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.dependencies import ROUTER_UNAVAILABLE_DETAIL
from app.routes import health, hotspot, pages, routers


_PUBLIC_ERROR_DETAILS = {
    status.HTTP_400_BAD_REQUEST: "Invalid request.",
    status.HTTP_401_UNAUTHORIZED: "Invalid username or password.",
    status.HTTP_403_FORBIDDEN: "Access denied.",
    status.HTTP_404_NOT_FOUND: "The requested resource was not found.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Method not allowed.",
    status.HTTP_409_CONFLICT: "The request could not be completed.",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "Invalid request.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too many requests. Please try again later.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "An internal server error occurred.",
    status.HTTP_502_BAD_GATEWAY: ROUTER_UNAVAILABLE_DETAIL,
    status.HTTP_503_SERVICE_UNAVAILABLE: ROUTER_UNAVAILABLE_DETAIL,
    status.HTTP_504_GATEWAY_TIMEOUT: ROUTER_UNAVAILABLE_DETAIL,
}


def _public_error_detail(status_code: int) -> str:
    return _PUBLIC_ERROR_DETAILS.get(status_code, "Request failed.")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="MikroTik Hotspot API", version="0.3.0")
    origins = settings.cors_origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(routers.router)
    application.include_router(hotspot.router)
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
