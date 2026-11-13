from rest_framework import status
from rest_framework.views import APIView

from accounts.permissions import HasBusinessAccess, IsOwner
from accounts.responses import error_response, success_response, validation_error_response

from .direct_rfq_docs import direct_rfq_create_docs
from .rfq_services import RFQCreationError, create_direct_rfqs
from .serializers import DirectRFQCreateSerializer, RFQDetailSerializer
from .throttles import DirectRFQThrottle
from .views import rfq_queryset


@direct_rfq_create_docs
class DirectRFQCreateApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]
  throttle_classes = [DirectRFQThrottle]

  def post(self, request):
    serializer = DirectRFQCreateSerializer(
      data=request.data, context={"business": request.business}
    )
    if not serializer.is_valid():
      return validation_error_response(serializer)
    data = serializer.validated_data
    try:
      rfqs = create_direct_rfqs(
        request.business,
        data["supplier"],
        data["items"],
        notes=data["notes"],
        created_by=request.user,
      )
    except RFQCreationError as exc:
      return error_response(exc.message, exc.code, status=status.HTTP_400_BAD_REQUEST)

    qs = rfq_queryset(request.business).filter(pk__in=[r.pk for r in rfqs]).order_by("number")
    return success_response(
      "RFQ sent.", RFQDetailSerializer(qs, many=True).data,
      status=status.HTTP_201_CREATED,
    )