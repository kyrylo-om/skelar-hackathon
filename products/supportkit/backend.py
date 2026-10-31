"""Helpers for the fake backends. Errors are JSON with a `detail`, which ApiClient passes on."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from .kit import CUSTOMER_HEADER


def customer_id(request: Request) -> int | None:
    value = request.headers.get(CUSTOMER_HEADER, "")
    return int(value) if value.isdigit() else None


def owned(records: dict, request: Request, key: str) -> dict | None:
    """The record named by path param `key` if it belongs to the caller. Not yours = not found."""
    record = records.get(request.path_params[key])
    if record is None or record["customer_id"] != customer_id(request):
        return None
    return record


def mine(records: dict, request: Request) -> list[dict]:
    return [r for r in records.values() if r["customer_id"] == customer_id(request)]


async def body(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status)


def not_found() -> JSONResponse:
    return error(404, "Не знайдено")
