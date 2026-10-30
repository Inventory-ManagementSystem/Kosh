import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from accounts.responses import error_response, success_response, validation_error_response
from accounts.swagger import err_example, ok_example, resp

from .serializers import ContactSerializer
from .tasks import send_contact_email

logger = logging.getLogger(__name__)

THANKS = "Thanks! We've received your message."


class ContactRateThrottle(AnonRateThrottle):
  scope = "contact"


class ContactApi(APIView):
  authentication_classes = [] 
  permission_classes = [AllowAny]
  throttle_classes = [ContactRateThrottle]

  @extend_schema(
    summary="Send a Contact Message",
    description=(
      "Public endpoint for the landing page contact form. The message is emailed "
      "to the Kosh team, with the visitor's email as Reply-To. Limited to 10 requests "
      "per hour per IP. `website` is a hidden spam trap: send it empty."
    ),
    request=ContactSerializer,
    responses={
      200: resp("Accepted.", ok_example("Sent", THANKS, data={"sent": True})),
      400: resp("Validation failed.",
                err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"email": ["Enter a valid email address."]})),
      429: resp("Too many requests from this IP.",
                err_example("Throttled",
                            "Request was throttled. Expected available in 3599 seconds.",
                            "THROTTLED")),
      503: resp("Could not queue the message.",
                err_example("Unavailable", "Could not send your message right now. "
                            "Please try again later.", "CONTACT_UNAVAILABLE")),
    },
  )
  def post(self, request):
    serializer = ContactSerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)
    data = serializer.validated_data

    if data.get("website"):
      return success_response(THANKS, {"sent": True})
    try:
      send_contact_email.delay(data["email"], data["message"])
    except Exception:
      logger.exception("Could not queue contact email")
      return error_response(
        "Could not send your message right now. Please try again later.",
        "CONTACT_UNAVAILABLE",
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
      )
    return success_response(THANKS, {"sent": True})
