from rest_framework.views import exception_handler

CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    429: "THROTTLED",
}


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    response.data = {
        "success": False,
        "message": str(detail) if detail else "Request failed.",
        "code": CODES.get(response.status_code, "ERROR"),
        "errors": None if detail else response.data,
        "details": None,
    }
    return response
