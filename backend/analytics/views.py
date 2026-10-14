from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from accounts.permissions import HasBusinessAccess, IsOwner
from accounts.responses import success_response

from . import services


def int_param(request, name, default, low, high):
  raw = request.query_params.get(name)
  if raw in (None, ""):
    return default
  try:
    value = int(raw)
  except ValueError:
    raise ValidationError({name: "Must be a whole number."})
  if not low <= value <= high:
    raise ValidationError({name: f"Must be between {low} and {high}."})
  return value


def days_param(name="days", default=30):
  return OpenApiParameter(
    name, OpenApiTypes.INT, OpenApiParameter.QUERY,
    description=f"Look-back window in days (1-365, default {default}).",
  )


LIMIT_PARAM = OpenApiParameter(
  "limit", OpenApiTypes.INT, OpenApiParameter.QUERY,
  description="Max rows to return (1-50, default 10).",
)


class AnalyticsView(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def days(self, request, default=30):
    return int_param(request, "days", default, 1, 365)

  def limit(self, request):
    return int_param(request, "limit", 10, 1, 50)


@extend_schema(tags=["Analytics"], summary="Dashboard KPI cards", parameters=[days_param()])
class OverviewApi(AnalyticsView):
  def get(self, request):
    data = services.overview(request.business, self.days(request))
    return success_response("Overview fetched.", data)


@extend_schema(tags=["Analytics"], summary="Stock status and value by category")
class StockBreakdownApi(AnalyticsView):
  def get(self, request):
    data = services.stock_breakdown(request.business)
    return success_response("Stock breakdown fetched.", data)


@extend_schema(tags=["Analytics"], summary="Daily stock in vs out", parameters=[days_param()])
class MovementTrendApi(AnalyticsView):
  def get(self, request):
    data = services.movement_trend(request.business, self.days(request))
    return success_response("Movement trend fetched.", data)


@extend_schema(
  tags=["Analytics"], summary="Most dispatched products",
  parameters=[days_param(), LIMIT_PARAM],
)
class TopProductsApi(AnalyticsView):
  def get(self, request):
    data = services.top_products(
      request.business, self.days(request), self.limit(request)
    )
    return success_response("Top products fetched.", data)


@extend_schema(
  tags=["Analytics"], summary="Slow-moving stock (no dispatch in N days)",
  parameters=[days_param(default=60), LIMIT_PARAM],
)
class SlowMovingApi(AnalyticsView):
  def get(self, request):
    data = services.slow_moving(
      request.business, self.days(request, default=60), self.limit(request)
    )
    return success_response("Slow-moving stock fetched.", data)


@extend_schema(
  tags=["Analytics"], summary="Days of stock cover (running out soon)",
  parameters=[LIMIT_PARAM],
)
class StockCoverApi(AnalyticsView):
  def get(self, request):
    data = services.stock_cover(request.business, self.limit(request))
    return success_response("Stock cover fetched.", data)


@extend_schema(tags=["Analytics"], summary="Dispatch by outlet", parameters=[days_param()])
class OutletDispatchApi(AnalyticsView):
  def get(self, request):
    data = services.outlet_dispatch(request.business, self.days(request))
    return success_response("Outlet dispatch fetched.", data)