from rest_framework import status
from rest_framework.views import APIView

from accounts.permissions import HasBusinessAccess, IsOwner
from accounts.responses import error_response, success_response

from .savings_docs import savings_summary_docs
from .savings_services import DEFAULT_DAYS, MAX_DAYS, savings_summary


@savings_summary_docs
class SavingsSummaryApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def get(self, request):
    try:
      days = int(request.query_params.get("days", DEFAULT_DAYS))
    except (TypeError, ValueError):
      days = 0
    if not 1 <= days <= MAX_DAYS:
      return error_response(
        f"days must be a whole number from 1 to {MAX_DAYS}.",
        "INVALID_PERIOD",
        status=status.HTTP_400_BAD_REQUEST,
      )
    return success_response("Savings fetched.", savings_summary(request.business, days))
