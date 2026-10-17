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

from .serializers import QuotationSubmitSerializer, RFQUpdateSerializer, RFQCreateSerializer, RFQUpdateSerializer, BulkRFQCreateSerializer


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
  "reorder_suggestion_ids": ["9e1b5c72-0a3d-4f86-b2c4-7d6a8e0f1b35"],
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
  "method": "manual",
  "status": "open",
  "rfq_id": None,
  "created_at": "2026-10-13T02:00:00Z",
}

ALERT_WITH_RFQ_EXAMPLE = {
  **ALERT_EXAMPLE,
  "method": "formula",
  "status": "rfq_created",
  "rfq_id": "c3d8a2f1-6b47-4e09-9a15-2f7e1b8d4c60",
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
      + RECIPIENT_NOTE + " `reorder_suggestion_ids` lists the low-stock alerts this RFQ covers."
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
      "RFQ returns a 400. The RFQ stays in the list with status `cancelled`, so the "
      "history is kept. If it was created from a low-stock alert, the alert goes "
      "back to `open`, so the owner can create a new RFQ from it. For a product with "
      "enough dispatch history, the nightly check creates a new RFQ automatically "
      "unless the alert is dismissed. Suppliers who had not declined get an in-app "
      "notification. No request body is needed. A cancelled RFQ cannot be reopened. "
      + OWNER_NOTE
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
      "stock state: `In Stock`, `Low Stock` or `Out of Stock`. `method` is "
      "`formula` when the product has enough dispatch history, in which case an RFQ "
      "is created automatically, and `manual` when it does not, in which case the "
      "owner decides with the Create RFQ action. `status` is `open` when no RFQ has "
      "been created yet and `rfq_created` once one has; `rfq_id` is then the id of "
      "that RFQ, otherwise null. " + ACCESS_NOTE
    ),
    parameters=PAGE_PARAMETERS,
    responses={
      200: resp(
        "Paginated alert list.",
        ok_example("Manual Alert", "Alerts fetched.", data=paginated(ALERT_EXAMPLE)),
        ok_example("Alert With RFQ", "Alerts fetched.", data=paginated(ALERT_WITH_RFQ_EXAMPLE)),
        ok_example("No Alerts", "Alerts fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: resp(
        "The page number is out of range.",
        err_example("Invalid Page", "Invalid page.", "NOT_FOUND"),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)



INVITATION_ID = "e5b93d40-1c7a-4f68-a2d9-6b0e8c4f7a13"
RFQ_ITEM_ID = "1f4a9d63-8c2e-47b0-a5d7-3e9b0c6a2f18"

SUPPLIER_RFQ_LIST_ITEM_EXAMPLE = {
  "id": INVITATION_ID,
  "rfq_id": "c3d8a2f1-6b47-4e09-9a15-2f7e1b8d4c60",
  "number": "RFQ-7568",
  "business_name": "Gupta Kirana",
  "business_city": "Delhi",
  "deadline": "2026-10-14T12:30:00Z",
  "rfq_status": "open",
  "my_status": "sent",
  "item_count": 1,
  "created_at": "2026-10-13T02:00:00Z",
}

QUOTATION_EXAMPLE = {
  "id": "6d2f8b14-93ae-4c57-b1e0-5a7c9d3f2e81",
  "status": "submitted",
  "revision": 1,
  "items": [
    {
      "id": "0b7e3c9a-2d41-4f85-a6c3-8e1f5d9b4a27",
      "rfq_item_id": RFQ_ITEM_ID,
      "product_name": "Amul Dahi",
      "sku": "SKU-787328",
      "requested_quantity": 70,
      "quantity": 70,
      "unit_price": "42.00",
      "gst_rate": "5.00",
      "line_subtotal": "2940.00",
      "line_tax": "147.00",
      "line_total": "3087.00",
    }
  ],
  "subtotal": "2940.00",
  "tax_total": "147.00",
  "grand_total": "3087.00",
  "advance_amount": "1000.00",
  "balance_amount": "2087.00",
  "delivery_date": "2026-10-15",
  "expected_delivery": "2026-10-15",
  "is_late": False,
  "late_by_days": 0,
  "valid_until": "2026-10-21",
  "notes": "Price includes transport within Delhi.",
  "submitted_at": "2026-10-13T12:50:00Z",
  "updated_at": "2026-10-13T12:50:00Z",
}

REVISED_QUOTATION_EXAMPLE = {
  **QUOTATION_EXAMPLE,
  "revision": 2,
  "delivery_date": "2026-10-17",
  "is_late": True,
  "late_by_days": 2,
  "updated_at": "2026-10-13T14:05:00Z",
}

SUPPLIER_RFQ_DETAIL_EXAMPLE = {
  **SUPPLIER_RFQ_LIST_ITEM_EXAMPLE,
  "my_status": "viewed",
  "notes": "",
  "items": [
    {"id": RFQ_ITEM_ID, "product_name": "Amul Dahi", "sku": "SKU-787328", "quantity": 70},
  ],
  "category": "Dairy",
  "product_name": "Amul Dahi",
  "sku": "SKU-787328",
  "required_quantity": 70,
  "expected_delivery": "2026-10-15",
  "can_quote": True,
  "my_quotation": None,
}

OWNER_QUOTATION_EXAMPLE = {
  **QUOTATION_EXAMPLE,
  "supplier_profile_id": "2c9f6a85-e7d1-4b03-9a58-4f1d8e3b6c70",
  "company_name": "Sharma Traders",
  "city": "Ghaziabad",
  "supplier_verified": True,
  "source": "own",
}

NOT_SUPPLIER_RESPONSE = resp(
  "The user has no supplier profile (owners and employees included).",
  err_example(
    "Not Supplier",
    "Register as a supplier before using this feature.",
    "FORBIDDEN",
  ),
)

INVITATION_NOT_FOUND_RESPONSE = resp(
  "No RFQ invitation with this id for the logged-in supplier. An invitation sent "
  "to another supplier also returns this.",
  err_example("Not Found", "RFQ not found.", "NOT_FOUND"),
)

RFQ_CLOSED_EXAMPLES = (
  err_example("RFQ Not Open", "This RFQ is no longer accepting quotations.", "RFQ_NOT_OPEN"),
  err_example("Deadline Passed", "The deadline for this RFQ has passed.", "RFQ_DEADLINE_PASSED"),
)

SUPPLIER_NOTE = (
  "Supplier only. Every supplier endpoint uses the invitation `id` from List My "
  "RFQs (not the RFQ id). A supplier only sees RFQs they were invited to."
)

WINDOW_NOTE = (
  "Changes are allowed only while the RFQ `status` is `open` and its `deadline` "
  "has not passed."
)

QUOTATION_FIELDS_NOTE = (
  "Totals are calculated by the server: `subtotal` = sum of unit price x quantity, "
  "`tax_total` = GST on each line, `grand_total` = subtotal + tax, "
  "`balance_amount` = grand total - advance (due on delivery). "
  "`expected_delivery` is the buyer's expected date; `is_late` / `late_by_days` "
  "say how far `delivery_date` is past it. A late date is allowed, it is only a warning."
)


supplier_rfq_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_rfqs_list",
    summary="Supplier: List My RFQs",
    description=(
      "The supplier's RFQ inbox, newest first, paginated. `id` is the invitation id "
      "used by every other supplier endpoint. `my_status` is `sent` (not opened yet), "
      "`viewed`, `quoted` or `declined`. `rfq_status` is the RFQ's own status. "
      + SUPPLIER_NOTE
    ),
    parameters=[
      OpenApiParameter(
        "status", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description="Filter by `my_status`: `sent`, `viewed`, `quoted` or `declined`.",
      ),
      OpenApiParameter(
        "open", OpenApiTypes.BOOL, OpenApiParameter.QUERY,
        description="`true` returns only RFQs that are open and before their deadline.",
      ),
      *PAGE_PARAMETERS,
    ],
    responses={
      200: resp(
        "Paginated invitation list.",
        ok_example("RFQs", "RFQs fetched.", data=paginated(SUPPLIER_RFQ_LIST_ITEM_EXAMPLE)),
        ok_example("No RFQs", "RFQs fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: resp(
        "The page number is out of range.",
        err_example("Invalid Page", "Invalid page.", "NOT_FOUND"),
      ),
    },
  ),
)

supplier_rfq_detail_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_rfqs_retrieve",
    summary="Supplier: Get RFQ",
    description=(
      "Everything the Post Quotation screen needs. Header card: `number`, "
      "`category`, `product_name`, `required_quantity`, `expected_delivery`, `sku`, "
      "`deadline` (quote by) and `business_name` / `business_city`. `items` holds "
      "the `id` to send as `rfq_item` when quoting. `can_quote` is false once the "
      "RFQ is closed, cancelled, awarded or past its deadline. `my_quotation` is the "
      "supplier's quotation, or null if they have not quoted. The first open "
      "changes `my_status` from `sent` to `viewed`, which the owner sees. "
      + SUPPLIER_NOTE
    ),
    responses={
      200: resp(
        "RFQ details.",
        ok_example("Not Quoted Yet", "RFQ fetched.", data=SUPPLIER_RFQ_DETAIL_EXAMPLE),
        ok_example("Already Quoted", "RFQ fetched.", data={
          **SUPPLIER_RFQ_DETAIL_EXAMPLE,
          "my_status": "quoted",
          "my_quotation": QUOTATION_EXAMPLE,
        }),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVITATION_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_quotation_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_quotation_retrieve",
    summary="Supplier: Get My Quotation",
    description=(
      "The supplier's quotation on this RFQ, including a withdrawn one. "
      + QUOTATION_FIELDS_NOTE + " " + SUPPLIER_NOTE
    ),
    responses={
      200: resp(
        "The quotation.",
        ok_example("Quotation", "Quotation fetched.", data=QUOTATION_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: resp(
        "No such invitation, or the supplier has not quoted yet.",
        err_example("Not Found", "RFQ not found.", "NOT_FOUND"),
        err_example("No Quotation", "You have not quoted on this RFQ yet.", "NO_QUOTATION"),
      ),
    },
  ),
  put=extend_schema(
    operation_id="procurement_supplier_quotation_submit",
    summary="Supplier: Post or Edit Quotation",
    description=(
      "Posts the quotation, or replaces it with a new revision. Always send the "
      "whole quotation. The first call returns 201 and later calls return 200 with "
      "`revision` increased. Posting again after a withdraw or decline works too. "
      + WINDOW_NOTE + "\n\n"
      "- `items`: one entry per RFQ item quoted. `rfq_item` is the item `id` from "
      "Supplier: Get RFQ. `unit_price` is per unit, excluding GST, at least 0.01. "
      "`gst_rate` is a percentage from 0 to 40 (default 0). `quantity` is optional, "
      "defaults to the requested quantity and cannot be more than it.\n"
      "- `advance_amount`: optional, default 0. Cannot be more than the total "
      "including GST.\n"
      "- `delivery_date`: required, `YYYY-MM-DD`, today or later.\n"
      "- `valid_until`: optional, `YYYY-MM-DD`. Defaults to 7 days after the RFQ "
      "deadline and cannot be before the deadline.\n"
      "- `notes`: optional remarks, up to 2000 characters.\n\n"
      + QUOTATION_FIELDS_NOTE + " The owner gets a notification. "
      + SUPPLIER_NOTE + " Accepts JSON."
    ),
    request=QuotationSubmitSerializer,
    examples=[
      OpenApiExample(
        "Post Quotation",
        value={
          "items": [{"rfq_item": RFQ_ITEM_ID, "unit_price": "42.00", "gst_rate": "5"}],
          "advance_amount": "1000.00",
          "delivery_date": "2026-10-15",
          "notes": "Price includes transport within Delhi.",
        },
        request_only=True,
      ),
      OpenApiExample(
        "Partial Quantity, No Advance",
        value={
          "items": [{
            "rfq_item": RFQ_ITEM_ID, "unit_price": "40.50", "gst_rate": "5", "quantity": 50,
          }],
          "delivery_date": "2026-10-16",
        },
        request_only=True,
      ),
    ],
    responses={
      200: resp(
        "Quotation revised.",
        ok_example("Revised", "Quotation revised.", data=REVISED_QUOTATION_EXAMPLE),
      ),
      201: resp(
        "Quotation posted.",
        ok_example("Posted", "Quotation submitted.", data=QUOTATION_EXAMPLE),
      ),
      400: resp(
        "Validation error, or the RFQ is not taking quotations.",
        err_example("Missing Fields", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": ["This field is required."],
          "delivery_date": ["This field is required."],
        }),
        err_example("Missing Price", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": [{"unit_price": ["This field is required."]}],
        }),
        err_example("Too Many Units", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": ["You can quote at most 70 units of Amul Dahi."],
        }),
        err_example("Wrong Item", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": [f"Item {RFQ_ITEM_ID} is not part of this RFQ."],
        }),
        err_example("Duplicate Item", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": ["Each RFQ item can be quoted only once."],
        }),
        err_example("GST Out Of Range", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": [{"gst_rate": ["Ensure this value is less than or equal to 40."]}],
        }),
        err_example("Advance Too High", "Validation failed.", "VALIDATION_ERROR", errors={
          "advance_amount": ["Advance payment cannot exceed the total amount (₹3087.00)."],
        }),
        err_example("Past Delivery Date", "Validation failed.", "VALIDATION_ERROR", errors={
          "delivery_date": ["Delivery date cannot be in the past."],
        }),
        err_example("Short Validity", "Validation failed.", "VALIDATION_ERROR", errors={
          "valid_until": [
            "Quotation must stay valid at least until the RFQ deadline (2026-10-14)."
          ],
        }),
        *RFQ_CLOSED_EXAMPLES,
        err_example(
          "Already Decided", "This quotation has already been decided.", "QUOTATION_DECIDED",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVITATION_NOT_FOUND_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
  delete=extend_schema(
    operation_id="procurement_supplier_quotation_withdraw",
    summary="Supplier: Withdraw Quotation",
    description=(
      "Withdraws the supplier's quotation. The owner no longer sees it and "
      "`my_status` goes back to `viewed`. The supplier can post again before the "
      "deadline. " + WINDOW_NOTE + " No request body. " + SUPPLIER_NOTE
    ),
    request=None,
    responses={
      200: resp("Quotation withdrawn.", ok_example("Withdrawn", "Quotation withdrawn.")),
      400: resp(
        "Nothing to withdraw, or the RFQ is not taking changes.",
        err_example(
          "No Active Quotation", "You have no active quotation on this RFQ.",
          "NO_ACTIVE_QUOTATION",
        ),
        *RFQ_CLOSED_EXAMPLES,
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVITATION_NOT_FOUND_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

supplier_rfq_decline_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_supplier_rfqs_decline",
    summary="Supplier: Decline RFQ",
    description=(
      "Tells the owner the supplier will not quote. `my_status` becomes `declined`. "
      "If the supplier has an active quotation they must withdraw it first. They "
      "can still post a quotation later, before the deadline. " + WINDOW_NOTE
      + " No request body. " + SUPPLIER_NOTE
    ),
    request=None,
    responses={
      200: resp("RFQ declined.", ok_example("Declined", "RFQ declined.")),
      400: resp(
        "Cannot decline.",
        err_example("Already Declined", "You have already declined this RFQ.", "ALREADY_DECLINED"),
        err_example(
          "Quotation Active", "Withdraw your quotation before declining.", "QUOTATION_ACTIVE",
        ),
        *RFQ_CLOSED_EXAMPLES,
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVITATION_NOT_FOUND_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

rfq_quotation_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_rfqs_quotations_list",
    summary="List Quotations for RFQ",
    description=(
      "Every quotation received on this RFQ, cheapest first (by `grand_total`, then "
      "earliest `submitted_at`), so the first entry is the lowest bid. Withdrawn "
      "quotations are left out. Not paginated. `source` is `own` for the owner's own "
      "supplier and `platform` for the platform pool. " + QUOTATION_FIELDS_NOTE
      + " " + ACCESS_NOTE
    ),
    responses={
      200: resp(
        "Quotations, cheapest first.",
        ok_example("Quotations", "Quotations fetched.", data=[
          OWNER_QUOTATION_EXAMPLE,
          {
            **OWNER_QUOTATION_EXAMPLE,
            "id": "93c1e7a4-5f20-4b8d-8e6a-1d4b7c0f9a35",
            "company_name": "Gupta Wholesale",
            "city": "Delhi",
            "source": "platform",
            "subtotal": "3080.00",
            "tax_total": "154.00",
            "grand_total": "3234.00",
            "advance_amount": "0.00",
            "balance_amount": "3234.00",
          },
        ]),
        ok_example("No Quotations Yet", "Quotations fetched.", data=[]),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
    },
  ),
)


ALERT_NOT_FOUND_RESPONSE = resp(
  "No such alert in this business. An alert that belongs to another business "
  "also returns this.",
  err_example("Not Found", "No ReorderSuggestion matches the given query.", "NOT_FOUND"),
)

ALERT_NOT_OPEN_EXAMPLE_TEXT = "The alert for Amul Milk 1L already has an RFQ or is closed."


reorder_alert_create_rfq_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_alerts_create_rfq",
    summary="Create RFQ From Alert",
    description=(
      "Creates an RFQ for the product of an open alert and sends it to the "
      "business's own suppliers. This is how the owner approves an alert whose "
      "`method` is `manual`; alerts with `formula` get their RFQ automatically. "
      "The product must have a supply category. The RFQ is sent to the business’s own suppliers that are active, "
      "linked to a supplier account, verified by an admin and registered for that supply category."
      "are skipped. All recipients get an in-app and push notification. The "
      "deadline is 3 days from now, `auto_generated` is false, and the alert "
      "becomes `rfq_created`. `quantity` is optional; when left out, the alert's "
      "`required_stock` is used. Set `include_platform_pool` to true to also send "
      "the RFQ to verified suppliers in the business's city (matched on the "
      "product's supply category); the default is false. Returns the full "
      "RFQ. " + OWNER_NOTE + " Accepts JSON; the body may be empty."
    ),
    request=RFQCreateSerializer,
    examples=[
      OpenApiExample("Use Suggested Quantity", value={}, request_only=True),
      OpenApiExample("Change Quantity", value={"quantity": 50}, request_only=True),
      OpenApiExample(
        "Include Platform Pool",
        value={"quantity": 50, "include_platform_pool": True},
        request_only=True,
      ),
    ],
    responses={
      201: resp(
        "RFQ created.",
        ok_example(
          "Created", "RFQ created.",
          data={**RFQ_DETAIL_EXAMPLE, "auto_generated": False},
        ),
      ),
      400: resp(
        "Validation error, or there is nobody to send the RFQ to.",
        err_example(
          "Quantity Too Low", "Validation failed.", "VALIDATION_ERROR",
          errors={"quantity": ["Ensure this value is greater than or equal to 1."]},
        ),
        err_example(
          "Quantity Too High", "Validation failed.", "VALIDATION_ERROR",
          errors={"quantity": ["Ensure this value is less than or equal to 1000000."]},
        ),
        err_example(
          "Invalid Quantity", "Validation failed.", "VALIDATION_ERROR",
          errors={"quantity": ["A valid integer is required."]},
        ),
        err_example(
          "Invalid Platform Pool", "Validation failed.", "VALIDATION_ERROR",
          errors={"include_platform_pool": ["Must be a valid boolean."]},
        ),
        err_example(
          "No Suppliers",
          "No verified suppliers found for Dairy.",
          "NO_SUPPLIERS",
        ),
        err_example(
          "No Supply Category",
          "Set a supply category on Amul Milk 1L so we know which suppliers to ask.",
          "NO_SUPPLY_CATEGORY",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: ALERT_NOT_FOUND_RESPONSE,
      409: resp(
        "The alert already has an RFQ, or it was dismissed.",
        err_example(
          "Alert Not Open", ALERT_NOT_OPEN_EXAMPLE_TEXT, "SUGGESTION_NOT_OPEN"
        ),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)

reorder_alert_dismiss_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_alerts_dismiss",
    summary="Dismiss Alert",
    description=(
      "Closes an alert the owner does not want to act on, so it leaves the Active "
      "Alerts list and stops counting as active. Only an alert with status `open` "
      "can be dismissed; one that already has an RFQ cannot, so delete or cancel "
      "the RFQ first. No request body is needed. A dismissed alert is not "
      "permanent: if the product is still low on stock, the nightly check creates "
      "a new alert for it. " + OWNER_NOTE
    ),
    request=None,
    responses={
      200: resp("Alert dismissed.", ok_example("Dismissed", "Alert dismissed.")),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: ALERT_NOT_FOUND_RESPONSE,
      409: resp(
        "The alert already has an RFQ, or it is already dismissed.",
        err_example(
          "Alert Not Open",
          "Only an alert without an RFQ can be dismissed.",
          "SUGGESTION_NOT_OPEN",
        ),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)

MULTI_ITEM_RFQ_EXAMPLE = {
  **RFQ_DETAIL_EXAMPLE,
  "auto_generated": False,
  "reorder_suggestion_ids": [
    "9e1b5c72-0a3d-4f86-b2c4-7d6a8e0f1b35",
    "4a7d1e95-b2c8-4036-9f5a-8e3c0d6b1a72",
  ],
  "items": [
    *RFQ_DETAIL_EXAMPLE["items"],
    {
      "id": "8c3e5a17-d204-4b69-93f1-6a0b7e2d9c45",
      "product": "a1b2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
      "product_name": "Amul Dahi",
      "sku": "SKU-787328",
      "category": "Dairy",
      "quantity": 70,
    },
  ],
}

reorder_alert_bulk_create_rfq_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_alerts_bulk_create_rfq",
    summary="Create RFQs From Several Alerts",
    description=(
      "Creates RFQs for several open alerts at once. The alerts are grouped by the "
      "product's supply category and one RFQ is created per category, so alerts in "
      "the same category share one RFQ with several items. Each RFQ goes only to "
      "verified suppliers who sell that category: the business's own suppliers (any "
      "location) and, if `include_platform_pool` is true, platform suppliers in the "
      "business's city. Every product must have a supply category. All or nothing: if "
      "any selected alert cannot be used, no RFQ is created. `alerts` holds 1 to 50 "
      "entries; each has the alert `id` and an optional `quantity` (defaults to the "
      "alert's `required_stock`). Returns a list with one RFQ per category. "
      "Each alert becomes `rfq_created`. The deadline is 3 days from now. "
      + OWNER_NOTE + " Accepts JSON."
    ),
    request=BulkRFQCreateSerializer,
    examples=[
      OpenApiExample(
        "Two Alerts",
        value={"alerts": [
          {"id": "9e1b5c72-0a3d-4f86-b2c4-7d6a8e0f1b35"},
          {"id": "4a7d1e95-b2c8-4036-9f5a-8e3c0d6b1a72", "quantity": 50},
        ]},
        request_only=True,
      ),
      OpenApiExample(
        "Include Platform Pool",
        value={
          "alerts": [{"id": "9e1b5c72-0a3d-4f86-b2c4-7d6a8e0f1b35"}],
          "include_platform_pool": True,
        },
        request_only=True,
      ),
    ],
    responses={
      201: resp(
        "RFQs created.",
        ok_example("Created", "RFQs created.", data=[MULTI_ITEM_RFQ_EXAMPLE]),
      ),
      400: resp(
        "Validation error, an alert cannot be used, or there is nobody to send to.",
        err_example("No Alerts", "Validation failed.", "VALIDATION_ERROR",
          errors={"alerts": ["This list may not be empty."]}),
        err_example("Duplicate Alert", "Validation failed.", "VALIDATION_ERROR",
          errors={"alerts": ["Each alert can be selected only once."]}),
        err_example("Too Many Alerts", "Validation failed.", "VALIDATION_ERROR",
          errors={"alerts": ["You can select at most 50 alerts at a time."]}),
        err_example("Invalid Alert Id", "Validation failed.", "VALIDATION_ERROR",
          errors={"alerts": [{"id": ["Must be a valid UUID."]}]}),
        err_example("Invalid Quantity", "Validation failed.", "VALIDATION_ERROR",
          errors={"alerts": [{"quantity": ["Ensure this value is greater than or equal to 1."]}]}),
        err_example(
          "No Supply Category",
          "Set a supply category on Amul Milk 1L so we know which suppliers to ask.",
          "NO_SUPPLY_CATEGORY",
        ),
        err_example(
          "No Suppliers", "No verified suppliers found for Dairy.", "NO_SUPPLIERS",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: resp(
        "A selected alert does not exist in this business.",
        err_example(
          "Alert Not Found", "One or more selected alerts were not found.", "ALERT_NOT_FOUND",
        ),
      ),
      409: resp(
        "A selected alert already has an RFQ, or it was dismissed.",
        err_example("Alert Not Open", ALERT_NOT_OPEN_EXAMPLE_TEXT, "SUGGESTION_NOT_OPEN"),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)

reorder_alert_refresh_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_alerts_refresh",
    summary="Refresh Alerts",
    description=(
      "Runs the low-stock check for the logged-in user's business right now, "
      "instead of waiting for the nightly check. A new alert is created for every "
      "active product that has reached its reorder point and has no active alert "
      "yet. Existing alerts are left alone, so calling it again is safe. It does not "
      "create any RFQ. `created` is how many new alerts this call made and "
      "`active_alerts` is the total number of active alerts afterwards. "
      "No request body is needed. " + OWNER_NOTE
    ),
    request=None,
    responses={
      200: resp(
        "Alerts refreshed.",
        ok_example(
          "New Alerts", "Alerts refreshed.",
          data={"created": 3, "active_alerts": 5},
        ),
        ok_example(
          "Nothing New", "Alerts refreshed.",
          data={"created": 0, "active_alerts": 5},
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
    },
  ),
)
