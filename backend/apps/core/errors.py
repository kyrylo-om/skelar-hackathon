from django.http import JsonResponse
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class Conflict(APIException):
    status_code = 409
    default_detail = "Стан змінився. Оновіть дані й повторіть запит."
    default_code = "state_conflict"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        code = getattr(exc, "default_code", "error")
        detail = response.data
        message = detail.get("detail") if isinstance(detail, dict) else None
        response.data = {"error": {"code": code, "message": str(message or "Некоректний запит." )}}
        if message is None:
            response.data["error"]["fields"] = detail
    return response


def csrf_failure(request, reason=""):
    return JsonResponse({"error": {"code": "csrf_failed", "message": "Потрібен коректний CSRF-токен."}}, status=403)
