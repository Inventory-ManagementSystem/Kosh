from drf_spectacular.utils import OpenApiExample, OpenApiResponse
from drf_spectacular.types import OpenApiTypes


def ok_example(name, message, data=None):
    return OpenApiExample(
        name,
        value={"success": True, "message": message, "data": data},
        response_only=True,
    )


def err_example(name, message, code, errors=None, details=None):
    return OpenApiExample(
        name,
        value={
            "success": False,
            "message": message,
            "code": code,
            "errors": errors,
            "details": details,
        },
        response_only=True,
    )


def resp(description, *examples):
    return OpenApiResponse(
        response=OpenApiTypes.OBJECT,
        description=description,
        examples=list(examples),
    )


THROTTLED_EXAMPLE = err_example(
    "Throttled",
    "Request was throttled. Expected available in 42 seconds.",
    "THROTTLED",
)

UNAUTHORIZED_RESPONSE = resp(
    "Missing, invalid or expired access token.",
    err_example(
        "Unauthorized",
        "Authentication credentials were not provided.",
        "UNAUTHORIZED",
    ),
)
