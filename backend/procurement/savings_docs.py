from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from accounts.swagger import UNAUTHORIZED_RESPONSE, err_example, ok_example, resp

from .SwaggerDocs import FORBIDDEN_RESPONSE, TAGS_RFQ

SAVINGS_NOTE = (
  "Estimated savings on this business's confirmed orders (issued, dispatched or "
  "received) created in the last `days` days. Cancelled orders and orders still "
  "waiting for their advance are left out. For each order, Kosh takes the other "
  "quotations that competed on the same RFQ (submitted or rejected, not "
  "withdrawn), averages their totals (GST included) and subtracts what was "
  "ordered. `savings` is positive when the order cost less than the average "
  "competing quote and negative when it cost more, so `total_savings` is a net "
  "figure. An order whose RFQ had no competing quote can't be compared; it is "
  "counted in `orders_without_competition` and left out of the totals. "
  "`savings_pct` is the saving as a percentage of the average competing total "
  "(overall: of the sum of the averages). This is an estimate against a "
  "benchmark, not a guaranteed saving: it ignores delivery dates, advance terms "
  "and credits for short or rejected goods. `orders` is newest first and not "
  "paginated. Owner only."
)

SAVINGS_ORDER_EXAMPLE = {
  "order_id": "2f6b9d04-7c1e-4a83-b5f2-9e0d3a8c6b17",
  "order_number": "PO-0001",
  "rfq_number": "RFQ-7568",
  "supplier_name": "Sharma Traders",
  "ordered_at": "2026-10-14T08:10:00Z",
  "order_total": "5292.00",
  "competing_quotes": 2,
  "average_competing_total": "5519.50",
  "savings": "227.50",
  "savings_pct": 4.1,
}

SAVINGS_COSTLIER_EXAMPLE = {
  "order_id": "7c1e4a93-2b60-4d58-9e07-3a8f6d2c1b45",
  "order_number": "PO-0002",
  "rfq_number": "RFQ-7560",
  "supplier_name": "Delhi Home and Personal Care",
  "ordered_at": "2026-10-11T15:30:00Z",
  "order_total": "8400.00",
  "competing_quotes": 1,
  "average_competing_total": "8200.00",
  "savings": "-200.00",
  "savings_pct": -2.4,
}

savings_summary_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS_RFQ,
    operation_id="procurement_savings_summary",
    summary="Estimated Savings",
    description=SAVINGS_NOTE,
    parameters=[
      OpenApiParameter(
        "days", OpenApiTypes.INT, OpenApiParameter.QUERY,
        description="Optional. Look-back period in days, 1 to 365. Default 90.",
      ),
    ],
    responses={
      200: resp(
        "Savings summary.",
        ok_example(
          "Savings", "Savings fetched.",
          data={
            "period_days": 90,
            "orders_compared": 2,
            "orders_without_competition": 1,
            "total_savings": "27.50",
            "savings_pct": 0.2,
            "orders": [SAVINGS_ORDER_EXAMPLE, SAVINGS_COSTLIER_EXAMPLE],
          },
        ),
        ok_example(
          "Nothing To Compare", "Savings fetched.",
          data={
            "period_days": 90,
            "orders_compared": 0,
            "orders_without_competition": 0,
            "total_savings": "0.00",
            "savings_pct": 0.0,
            "orders": [],
          },
        ),
      ),
      400: resp(
        "The period is invalid.",
        err_example(
          "Invalid Period", "days must be a whole number from 1 to 365.", "INVALID_PERIOD",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
    },
  ),
)
