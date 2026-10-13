from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
  extend_schema,
  extend_schema_view,
  OpenApiExample,
  OpenApiParameter,
)

from accounts.swagger import (
  ok_example,
  err_example,
  resp,
  THROTTLED_EXAMPLE,
  UNAUTHORIZED_RESPONSE,
)

from .serializers import RFQUpdateSerializer


RFQ_LIST_ITEM_EXAMPLE = {
  "id": "c3d8a2f1-6b47-4e09-9a15-2f7e1b8d4c60",
  "number": "RFQ-0007",
  "status": "open",
  "deadline": "2026-10-16T18:30:00Z",
  "include_platform_pool": False,
  "auto_generated": True,
  "product_name": "Amul Milk 1L",
  "sku": "SKU-202",
  "category": "Dairy",
  "quantity": 70,
  "expected_delivery": "2026-10-20",
  "recipient_count": 3,
  "quoted_count": 1,
  "created_at": "2026-10-13T02:00:00Z",
}

RFQ_DETAIL_EXAMPLE = {
  **RFQ_LIST_ITEM_EXAMPLE,
  "notes": "",
  "reorder_suggestion_id": "9e1b5c72-0a3d-4f86-b2c4-7d6a8e0f1b35",
  "items": [
    {
      "id": "1f4a9d63-8c2e-47b0-a5d7-3e9b0c6a2f18",
      "product": "5d0c7e91-4b3a-4a28-8f16-c2e9a7b1d054",
      "product_name": "Amul Milk 1L",
      "sku": "SKU-202",
      "category": "Dairy",
      "quantity": 70,
    }
  ],
  "recipients": [
    {
      "id": "7a2c6e18-d3f5-4b91-9c04-e8a1b5d73f26",
      "supplier_profile_id": "b84e1f07-5a9c-4d32-86e1-0c7d3a9f5b42",
      "company_name": "Gupta Wholesale",
      "city": "Delhi",
      "source": "own",
      "status": "quoted",
      "viewed_at": "2026-10-13T04:10:00Z",
      "responded_at": "2026-10-13T06:45:00Z",
    },
    {
      "id": "e5b93d40-1c7a-4f68-a2d9-6b0e8c4f7a13",
      "supplier_profile_id": "2c9f6a85-e7d1-4b03-9a58-4f1d8e3b6c70",
      "company_name": "Sharma Traders",
      "city": "Ghaziabad",
      "source": "own",
      "status": "sent",
      "viewed_at": None,
      "responded_at": None,
    },
  ],
  "updated_at": "2026-10-13T06:45:00Z",
}

ALERT_EXAMPLE = {
  "id": "4a7d1e95-b2c8-4036-9f5a-8e3c0d6b1a72",
  "product_id": "5d0c7e91-4b3a-4a28-8f16-c2e9a7b1d054",
  "product_name": "Amul Milk 1L",
  "sku": "SKU-202",
  "category": "Dairy",
  "required_stock": 30,
  "stock_status": "Low Stock",
  "status": "open",
  "created_at": "2026-10-13T02:00:00Z",
}


def paginated(*results):
  return {
    "count": len(results),
    "next": None,
    "previous": None,
    "results": list(results),
  }


NO_BUSINESS_EXAMPLE = err_example(
  "No Business",
  "Register your business or join one before using this feature.",
  "FORBIDDEN",
)

FORBIDDEN_RESPONSE = resp(
  "The user neither owns nor works for a business (this includes supplier accounts).",
  NO_BUSINESS_EXAMPLE,
)

OWNER_ONLY_RESPONSE = resp(
  "The user has no business, or is an employee. Only the owner can make this change.",
  NO_BUSINESS_EXAMPLE,
  err_example(
    "Not Owner",
    "Only the business owner can perform this action.",
    "FORBIDDEN",
  ),
)

THROTTLED_RESPONSE = resp("Too many requests.", THROTTLED_EXAMPLE)

NOT_FOUND_RESPONSE = resp(
  "No such RFQ in this business. An RFQ that belongs to another business also returns this.",
  err_example("Not Found", "No RFQ matches the given query.", "NOT_FOUND"),
)


def validation_cases(*cases):
  return resp(
    "Validation error.",
    *[
      err_example(name, "Validation failed.", "VALIDATION_ERROR", errors=errors)
      for name, errors in cases
    ],
  )


ACCESS_NOTE = "Both the owner and employees can read it."

OWNER_NOTE = "Owner only; employees get a 403."

RFQ_NOTE = (
  "An RFQ (request for quotation) is created automatically by the nightly low-stock "
  "check when a product's stock falls to its reorder point and the reorder quantity "
  "was calculated from dispatch history. It asks suppliers to quote for one product "
  "and quantity. `auto_generated` is true when the system created it."
)

STATUS_NOTE = (
  "`status` is `open` while suppliers can still send quotations, `closed` once the "
  "deadline has passed, `awarded` after a quotation is selected and `cancelled` if "
  "the owner cancelled it."
)

CARD_NOTE = (
  "`quantity` is the amount to order. `expected_delivery` is an estimate: the day "
  "the RFQ was created plus the product's lead time in days. `category` is null if "
  "the product has no category. `recipient_count` is the number of suppliers the RFQ "
  "was sent to and `quoted_count` is how many of them have sent a quotation."
)

RECIPIENT_NOTE = (
  "Each recipient has a `source` (`own` for the owner's own supplier, `platform` "
  "for the verified platform pool) and a `status` (`sent`, `viewed`, `quoted` or "
  "`declined`)."
)

PAGE_PARAMETERS = [
  OpenApiParameter(
    "page", OpenApiTypes.INT, OpenApiParameter.QUERY,
    description="Page number, starting at 1. An out-of-range page returns a 404.",
  ),
  OpenApiParameter(
    "page_size", OpenApiTypes.INT, OpenApiParameter.QUERY,
    description="Items per page. Default 10, maximum 50.",
  ),
]


rfq_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_rfqs_list",
    summary="List RFQs",
    description=(
      "Returns the RFQs of the logged-in user's business, newest first, paginated. "
      "This feeds the 'All RFQ' cards on the RFQ & Alerts screen. " + ACCESS_NOTE
      + " " + RFQ_NOTE + " " + STATUS_NOTE + " " + CARD_NOTE
    ),
    parameters=[
      OpenApiParameter(
        "status", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description=(
          "`open`, `closed`, `awarded` or `cancelled`. Any other value is ignored "
          "and all RFQs are returned."
        ),
      ),
      *PAGE_PARAMETERS,
    ],
    responses={
      200: resp(
        "Paginated RFQ list.",
        ok_example("RFQs", "RFQs fetched.", data=paginated(RFQ_LIST_ITEM_EXAMPLE)),
        ok_example("No RFQs", "RFQs fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: resp(
        "The page number is out of range.",
        err_example("Invalid Page", "Invalid page.", "NOT_FOUND"),
      ),
    },
  ),
)

rfq_detail_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_rfqs_retrieve",
    summary="Get RFQ",
    description=(
      "Returns one RFQ with its product line and the list of suppliers it was sent "
      "to. " + ACCESS_NOTE + " " + STATUS_NOTE + " " + CARD_NOTE + " "
      + RECIPIENT_NOTE + " `reorder_suggestion_id` is the low-stock alert that "
      "caused the RFQ."
    ),
    responses={
      200: resp(
        "RFQ details.",
        ok_example("RFQ", "RFQ fetched.", data=RFQ_DETAIL_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
    },
  ),
  patch=extend_schema(
    summary="Update RFQ",
    description=(
      "Partial update. Send only the fields you want to change; there is no PUT. "
      "You can change `deadline` (the last time suppliers can send a quotation, "
      "which must be in the future) and `notes`. Only an RFQ whose status is "
      "`open` can be edited. Recipients, products and quantities cannot be changed. "
      "Returns the full RFQ. " + OWNER_NOTE + " Accepts JSON."
    ),
    request=RFQUpdateSerializer,
    examples=[
      OpenApiExample(
        "Extend Deadline",
        value={"deadline": "2026-10-20T18:30:00Z"},
        request_only=True,
      ),
      OpenApiExample(
        "Add Note",
        value={"notes": "Delivery needed before the festival week."},
        request_only=True,
      ),
    ],
    responses={
      200: resp(
        "RFQ updated.",
        ok_example("Updated", "RFQ updated.", data=RFQ_DETAIL_EXAMPLE),
      ),
      400: validation_cases(
        ("Past Deadline", {"deadline": ["Deadline must be in the future."]}),
        (
          "Invalid Deadline",
          {"deadline": [
            "Datetime has wrong format. Use one of these formats instead: "
            "YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z]."
          ]},
        ),
        ("Null Deadline", {"deadline": ["This field may not be null."]}),
        ("Invalid Notes", {"notes": ["Not a valid string."]}),
        ("RFQ Not Open", {"non_field_errors": ["Only an open RFQ can be edited."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: NOT_FOUND_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

rfq_cancel_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_rfqs_cancel",
    summary="Cancel RFQ",
    description=(
      "Cancels an RFQ so suppliers can no longer send quotations. Only an RFQ whose "
      "status is `open` can be cancelled; an awarded, closed or already cancelled "
      "RFQ returns a 400. No request body is needed. A cancelled RFQ cannot be "
      "reopened. " + OWNER_NOTE
    ),
    request=None,
    responses={
      200: resp("RFQ cancelled.", ok_example("Cancelled", "RFQ cancelled.")),
      400: resp(
        "The RFQ is not open.",
        err_example(
          "Not Open",
          "Only an open RFQ can be cancelled.",
          "RFQ_NOT_OPEN",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: NOT_FOUND_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

rfq_summary_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_rfqs_summary",
    summary="RFQ Summary",
    description=(
      "Returns the three counts shown at the top of the RFQ & Alerts screen. "
      "`total_monthly_rfq` is the number of RFQs created this calendar month (UTC), "
      "`approved_quotations` is how many of those RFQs have been awarded, and "
      "`active_alerts` is the number of low-stock alerts that are still open, "
      "whether or not an RFQ has been created for them. " + ACCESS_NOTE
    ),
    responses={
      200: resp(
        "Summary counts.",
        ok_example(
          "Summary", "Summary fetched.",
          data={"total_monthly_rfq": 14, "approved_quotations": 8, "active_alerts": 4},
        ),
        ok_example(
          "Nothing Yet", "Summary fetched.",
          data={"total_monthly_rfq": 0, "approved_quotations": 0, "active_alerts": 0},
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
    },
  ),
)

reorder_alert_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_alerts_list",
    summary="List Active Alerts",
    description=(
      "Returns the active low-stock alerts of the business, newest first, "
      "paginated. This feeds the Active Alerts table. An alert is created by the "
      "nightly low-stock check and stays active until it is closed. `required_stock` "
      "is the suggested quantity to order. `stock_status` is the product's current "
      "stock state: `In Stock`, `Low Stock` or `Out of Stock`. `status` is `open` "
      "when no RFQ has been created yet and `rfq_created` once one has. " + ACCESS_NOTE
    ),
    parameters=PAGE_PARAMETERS,
    responses={
      200: resp(
        "Paginated alert list.",
        ok_example("Alerts", "Alerts fetched.", data=paginated(ALERT_EXAMPLE)),
        ok_example("No Alerts", "Alerts fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: resp(
        "The page number is out of range.",
        err_example("Invalid Page", "Invalid page.", "NOT_FOUND"),
      ),
    },
  ),
)
