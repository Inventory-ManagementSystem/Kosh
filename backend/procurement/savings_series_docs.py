from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from accounts.swagger import UNAUTHORIZED_RESPONSE, err_example, ok_example, resp

from .SwaggerDocs import FORBIDDEN_RESPONSE

SERIES_NOTE = (
  "Estimated savings over time, for the dashboard chart. It uses the same "
  "calculation as `GET /savings/`: each confirmed order is compared with the "
  "average of the other quotations on its RFQ, and the totals here always match "
  "that endpoint for the same `days`. Orders are placed in the period in which "
  "they were created (UTC dates). `points` has one entry for every day, week or "
  "month in the window, oldest first, including periods with no orders "
  "(`savings` 0.00, `orders` 0), so a chart can draw it without filling gaps. "
  "`period_start` is the first day of that period; weeks start on Monday, and the "
  "first week or month can begin a few days before the window does (only orders "
  "inside the window are counted in it). `savings` is the net saving of that "
  "period, negative when orders cost more than the average competing quote, and "
  "`cumulative` is the running total up to and including it. The last point's "
  "`cumulative` equals `total_savings`. `group_by` defaults from `days`: `day` up "
  "to 31 days, `week` up to 120, otherwise `month`. `savings_pct` and the two "
  "order counts are the same as in `/savings/`; orders whose RFQ had no competing "
  "quote can't be compared, are counted in `orders_without_competition` and add "
  "nothing to the chart. These are estimates against a benchmark, not guaranteed "
  "savings. Owner only. Not paginated."
)

SERIES_WEEKLY_EXAMPLE = {
  "period_days": 90,
  "group_by": "week",
  "orders_compared": 3,
  "orders_without_competition": 3,
  "total_savings": "6069.53",
  "savings_pct": 3.7,
  "points": [
    {"period_start": "2026-09-28", "savings": "2672.78", "cumulative": "2672.78", "orders": 1},
    {"period_start": "2026-10-05", "savings": "0.00", "cumulative": "2672.78", "orders": 0},
    {"period_start": "2026-10-12", "savings": "2310.00", "cumulative": "4982.78", "orders": 1},
    {"period_start": "2026-10-19", "savings": "0.00", "cumulative": "4982.78", "orders": 0},
    {"period_start": "2026-10-26", "savings": "1086.75", "cumulative": "6069.53", "orders": 1},
  ],
}

SERIES_NEGATIVE_EXAMPLE = {
  "period_days": 30,
  "group_by": "day",
  "orders_compared": 2,
  "orders_without_competition": 0,
  "total_savings": "1248.20",
  "savings_pct": -2.1,
  "points": [
    {"period_start": "2026-10-12", "savings": "1450.00", "cumulative": "1450.00", "orders": 1},
    {"period_start": "2026-10-13", "savings": "0.00", "cumulative": "1450.00", "orders": 0},
    {"period_start": "2026-10-14", "savings": "-201.80", "cumulative": "1248.20", "orders": 1},
  ],
}

SERIES_EMPTY_EXAMPLE = {
  "period_days": 7,
  "group_by": "day",
  "orders_compared": 0,
  "orders_without_competition": 0,
  "total_savings": "0.00",
  "savings_pct": 0.0,
  "points": [
    {"period_start": "2026-11-05", "savings": "0.00", "cumulative": "0.00", "orders": 0},
    {"period_start": "2026-11-06", "savings": "0.00", "cumulative": "0.00", "orders": 0},
  ],
}

TAG_SAVING=["Savings Time Series Chart"]

savings_series_docs = extend_schema_view(
  get=extend_schema(
    tags=TAG_SAVING,
    operation_id="procurement_savings_series",
    summary="Estimated Savings Over Time",
    description=SERIES_NOTE,
    parameters=[
      OpenApiParameter(
        "days", OpenApiTypes.INT, OpenApiParameter.QUERY,
        description=(
          "Optional. Look-back period in days, 1 to 365. Default 90. The dashboard "
          "toggle sends 7, 30, 90 or 365."
        ),
      ),
      OpenApiParameter(
        "group_by", OpenApiTypes.STR, OpenApiParameter.QUERY,
        enum=["day", "week", "month"],
        description=(
          "Optional. Size of each point. By default it follows `days`: `day` up to "
          "31 days, `week` up to 120 days, otherwise `month`."
        ),
      ),
    ],
    responses={
      200: resp(
        "Savings over time.",
        ok_example(
          "Weekly, 90 Days (points shortened)", "Savings series fetched.",
          data=SERIES_WEEKLY_EXAMPLE,
        ),
        ok_example(
          "Negative Period (points shortened)", "Savings series fetched.",
          data=SERIES_NEGATIVE_EXAMPLE,
        ),
        ok_example(
          "Nothing To Compare (points shortened)", "Savings series fetched.",
          data=SERIES_EMPTY_EXAMPLE,
        ),
      ),
      400: resp(
        "The period or the grouping is invalid.",
        err_example(
          "Invalid Period", "days must be a whole number from 1 to 365.", "INVALID_PERIOD",
        ),
        err_example(
          "Invalid Group", "group_by must be day, week or month.", "INVALID_GROUP",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
    },
  ),
)
