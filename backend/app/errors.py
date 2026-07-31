from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from .request_context import get_request_id


STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    500: "internal_error",
}


def error_payload(code: str, message: str, details=None) -> dict:
    return {
        "code": code,
        "message": message,
        "details": details,
        "request_id": get_request_id(),
    }


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    message = detail.get("message", "request failed") if isinstance(detail, dict) else str(detail)
    details = detail if isinstance(detail, dict) else None
    code = STATUS_CODES.get(exc.status_code, "http_error")
    return JSONResponse(status_code=exc.status_code, content=error_payload(code, message, details))


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload("validation_error", "request validation failed", exc.errors()),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload("internal_error", "internal server error", {"type": type(exc).__name__}),
    )
