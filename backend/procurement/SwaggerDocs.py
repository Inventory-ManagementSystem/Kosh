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

from .serializers import QuotationSubmitSerializer, RFQUpdateSerializer, RFQCreateSerializer, RFQUpdateSerializer, BulkRFQCreateSerializer, DispatchSerializer, AdvanceVerifySerializer


RFQ_ITEMS_EXAMPLE = [
  {
    "id": "1f4a9d63-8c2e-47b0-a5d7-3e9b0c6a2f18",
    "product": "5d0c7e91-4b3a-4a28-8f16-c2e9a7b1d054",
    "product_name": "Amul Dahi",
    "sku": "SKU-787328",
    "category": "Dairy",
    "supply_category": "Dairy",
    "quantity": 70,
  },
  {
    "id": "8c3e5a17-d204-4b69-93f1-6a0b7e2d9c45",
    "product": "a1b2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
    "product_name": "Amul Milk 1L",
    "sku": "SKU-202",
    "category": "Dairy",
    "supply_category": "Dairy",
    "quantity": 70,
  },
]

RFQ_LIST_ITEM_EXAMPLE = {
  "id": "c3d8a2f1-6b47-4e09-9a15-2f7e1b8d4c60",
  "number": "RFQ-0007",
  "status": "open",
  "deadline": "2026-10-16T18:30:00Z",
  "include_platform_pool": False,
  "auto_generated": True,
  "supply_category": "Dairy",
  "item_count": 2,
  "total_quantity": 140,
  "items": RFQ_ITEMS_EXAMPLE,
  "expected_delivery": "2026-10-20",
  "recipient_count": 3,
  "quoted_count": 1,
  "created_at": "2026-10-13T02:00:00Z",
}

RFQ_DETAIL_EXAMPLE = {
  **RFQ_LIST_ITEM_EXAMPLE,
  "notes": "",
  "reorder_suggestion_ids": [
    "9e1b5c72-0a3d-4f86-b2c4-7d6a8e0f1b35",
    "4a7d1e95-b2c8-4036-9f5a-8e3c0d6b1a72",
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
  "supply_category": "Dairy",
  "supply_category_id": 3,
  "required_stock": 30,
  "price": "60.00",
  "cost_price": "52.00",
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
  "An RFQ (request for quotation) asks suppliers to quote for one or more products "
  "of the same supply category. It is created automatically by the nightly low-stock "
  "check, or by the owner from the Active Alerts table. `auto_generated` is true "
  "when the system created it."
)

STATUS_NOTE = (
  "`status` is `open` while suppliers can still send quotations, `closed` once the "
  "deadline has passed, `awarded` after a quotation is selected and `cancelled` if "
  "the owner cancelled it."
)

CARD_NOTE = (
  "`items` lists every product and quantity requested; `item_count` and "
  "`total_quantity` summarise them. `supply_category` is the kind of supplier the "
  "RFQ was sent to (null for RFQs created before supply categories existed). "
  "`expected_delivery` is an estimate: the day the RFQ was created plus the longest "
  "lead time among its products. `recipient_count` is the number of suppliers the "
  "RFQ was sent to and `quoted_count` is how many of them have sent a quotation."
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
      "Returns one RFQ with its product lines and the list of suppliers it was sent "
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
      "Cancels an RFQ so suppliers can no longer send quotations. An RFQ whose "
      "status is `open`, or `closed` (the deadline passed and nobody was chosen), "
      "can be cancelled; an awarded or already cancelled RFQ returns a 400. The RFQ "
      "stays in the list with status `cancelled`, so the history is kept. If it was "
      "created from a low-stock alert, the alert goes back to `open`, so the owner "
      "can create a new RFQ from it. For a product with enough dispatch history, the "
      "nightly check creates a new RFQ automatically unless the alert is dismissed. "
      "Suppliers who had not declined get an in-app notification. No request body is "
      "needed. A cancelled RFQ cannot be reopened. To undo an accepted quotation "
      "whose advance is unpaid, cancel the order instead. " + OWNER_NOTE
    ),
    request=None,
    responses={
      200: resp("RFQ cancelled.", ok_example("Cancelled", "RFQ cancelled.")),
      400: resp(
        "The RFQ is awarded or already cancelled.",
        err_example(
          "Not Open Or Closed",
          "Only an open or closed RFQ can be cancelled.",
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
      "that RFQ, otherwise null. " 
      "`price` is the product's selling price per unit and `cost_price` is what the "
      "business pays per unit; `cost_price` is null if it hasn't been entered. " + ACCESS_NOTE
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
RFQ_ITEM_ID_2 = "8c3e5a17-d204-4b69-93f1-6a0b7e2d9c45"

SUPPLIER_RFQ_LIST_ITEM_EXAMPLE = {
  "id": INVITATION_ID,
  "rfq_id": "c3d8a2f1-6b47-4e09-9a15-2f7e1b8d4c60",
  "number": "RFQ-7568",
  "business_name": "Gupta Kirana",
  "business_city": "Delhi",
  "supply_category": "Dairy",
  "deadline": "2026-10-14T12:30:00Z",
  "rfq_status": "open",
  "my_status": "sent",
  "item_count": 2,
  "total_quantity": 140,
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
    },
    {
      "id": "c5d9a2e7-4b18-4f63-9e0a-7d2c1b8f3a56",
      "rfq_item_id": RFQ_ITEM_ID_2,
      "product_name": "Amul Milk 1L",
      "sku": "SKU-202",
      "requested_quantity": 70,
      "quantity": 70,
      "unit_price": "30.00",
      "gst_rate": "5.00",
      "line_subtotal": "2100.00",
      "line_tax": "105.00",
      "line_total": "2205.00",
    },
  ],

  "subtotal": "5040.00",
  "tax_total": "252.00",
  "grand_total": "5292.00",
  "advance_amount": "1000.00",
  "balance_amount": "4292.00",
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
    {
      "id": "8c3e5a17-d204-4b69-93f1-6a0b7e2d9c45",
      "product_name": "Amul Milk 1L", "sku": "SKU-202", "quantity": 70,
    },
  ],
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
  "rank": 1,
  "score": 97.8,
  "badges": ["recommended", "cheapest", "fastest"],
  "breakdown": {
    "price": {"score": 100.0, "weight": 58.8},
    "delivery": {"score": 100.0, "weight": 29.4},
    "payment": {"score": 81.1, "weight": 11.8},
    "reliability": {"score": None, "weight": 0.0},
  },
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
  "A quotation must cover every item on the RFQ at the full requested quantity; "
  "there are no partial quotes. "
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
      "`supply_category`, `item_count`, `total_quantity`, `expected_delivery`, "
      "`deadline` (quote by) and `business_name` / `business_city`. `items` lists "
      "every product the business wants, each with the `id` to send as `rfq_item` "
      "when quoting. `can_quote` is false once the RFQ is closed, cancelled, "
      "awarded or past its deadline. `my_quotation` is the supplier's quotation, "
      "or null if they have not quoted. The first open changes `my_status` from "
      "`sent` to `viewed`, which the owner sees. " + SUPPLIER_NOTE
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
      "- `items`: one entry for EVERY item on the RFQ, always at the full requested "
      "quantity (no partial quotes). `rfq_item` is the item `id` from Supplier: Get "
      "RFQ. `unit_price` is per unit, excluding GST, at least 0.01. `gst_rate` is a "
      "percentage from 0 to 40 (default 0). `quantity` is not needed; if you send it, "
      "it must equal the requested quantity.\n"
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
          "items": [
            {"rfq_item": RFQ_ITEM_ID, "unit_price": "42.00", "gst_rate": "5"},
            {"rfq_item": RFQ_ITEM_ID_2, "unit_price": "30.00", "gst_rate": "5"},
          ],
          "advance_amount": "1000.00",
          "delivery_date": "2026-10-15",
          "notes": "Price includes transport within Delhi.",
        },
        request_only=True,
      ),
      OpenApiExample(
        "No Advance",
        value={
          "items": [
            {"rfq_item": RFQ_ITEM_ID, "unit_price": "40.50", "gst_rate": "5"},
            {"rfq_item": RFQ_ITEM_ID_2, "unit_price": "29.00", "gst_rate": "12"},
          ],
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
        err_example("Partial Quantity", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": ["Quote the full quantity: 70 units of Amul Dahi."],
        }),
        err_example("Missing Item", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": ["Quote every product on this RFQ. Missing: Amul Milk 1L."],
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
          "advance_amount": ["Advance payment cannot exceed the total amount (₹5292.00)."],
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

RANKING_NOTE = (
  "Quotations come back ranked, best first, with a `score` from 0 to 100 and a "
  "`rank`. The score blends four parameters, each compared with the other quotations "
  "on this RFQ: `price` (grand total; the lowest scores 100), `delivery` (days from "
  "the RFQ's creation to the quoted delivery date; the earliest scores 100), "
  "`payment` (a smaller advance scores higher; no advance is 100) and `reliability` "
  "(the supplier's delivery record; it is left out while nobody has any history). "
  "Default weights are price 50, delivery 25, payment 10 and reliability 15. A "
  "parameter that can't be scored is skipped and its weight is shared among the "
  "others. `breakdown` shows each parameter's score and its effective weight in "
  "percent. `badges` can include `recommended` (rank 1), `cheapest` and `fastest`. "
  "Scores are calculated on every call and change when quotations are added, "
  "revised or withdrawn. The ranking is only a suggestion; the owner decides."
)

rfq_quotation_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_rfqs_quotations_list",
    summary="List Quotations for RFQ",
    description=(
      "Every quotation received on this RFQ, ranked by score, best first. Withdrawn "
      "quotations are left out. Not paginated. `source` is `own` for the owner's own "
      "supplier and `platform` for the platform pool. " + RANKING_NOTE + " "
      + QUOTATION_FIELDS_NOTE + " " + ACCESS_NOTE
    ),
    parameters=[
      OpenApiParameter(
        "weight_price", OpenApiTypes.FLOAT, OpenApiParameter.QUERY,
        description=(
          "Optional. Priority of price, 0 to 1000. Weights are relative, so 70/30 "
          "and 7/3 mean the same. If you send any weight, the ones you leave out "
          "count as 0; if you send none, the defaults are used."
        ),
      ),
      OpenApiParameter(
        "weight_delivery", OpenApiTypes.FLOAT, OpenApiParameter.QUERY,
        description="Optional. Priority of delivery date, 0 to 1000.",
      ),
      OpenApiParameter(
        "weight_payment", OpenApiTypes.FLOAT, OpenApiParameter.QUERY,
        description="Optional. Priority of payment terms (small advance), 0 to 1000.",
      ),
      OpenApiParameter(
        "weight_reliability", OpenApiTypes.FLOAT, OpenApiParameter.QUERY,
        description="Optional. Priority of supplier reliability, 0 to 1000.",
      ),
      OpenApiParameter(
        "sort", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description=(
          "Optional. `rank` (default) or `price` (cheapest first). Only the order "
          "of the list changes; `rank` and `score` stay the same."
        ),
      ),
    ],
    responses={
      200: resp(
        "Quotations, best first.",
        ok_example("Quotations", "Quotations fetched.", data=[
          OWNER_QUOTATION_EXAMPLE,
          {
            **OWNER_QUOTATION_EXAMPLE,
            "id": "93c1e7a4-5f20-4b8d-8e6a-1d4b7c0f9a35",
            "company_name": "Gupta Wholesale",
            "city": "Delhi",
            "source": "platform",
            "subtotal": "5180.00",
            "tax_total": "259.00",
            "grand_total": "5439.00",
            "advance_amount": "0.00",
            "balance_amount": "5439.00",
            "delivery_date": "2026-10-16",
            "is_late": True,
            "late_by_days": 1,
            "rank": 2,
            "score": 88.6,
            "badges": [],
            "breakdown": {
              "price": {"score": 97.3, "weight": 58.8},
              "delivery": {"score": 66.7, "weight": 29.4},
              "payment": {"score": 100.0, "weight": 11.8},
              "reliability": {"score": None, "weight": 0.0},
            },
          },
        ]),
        ok_example("No Quotations Yet", "Quotations fetched.", data=[]),
      ),
      400: resp(
        "A weight is invalid.",
        err_example(
          "Invalid Weight",
          "weight_price must be a number from 0 to 1000.",
          "INVALID_WEIGHTS",
        ),
        err_example(
          "No Usable Weight",
          "Give at least one scorable parameter a weight above 0.",
          "INVALID_WEIGHTS",
        ),
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

MULTI_ITEM_RFQ_EXAMPLE = {**RFQ_DETAIL_EXAMPLE, "auto_generated": False}

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

PURCHASE_ORDER_EXAMPLE = {
  "id": "2f6b9d04-7c1e-4a83-b5f2-9e0d3a8c6b17",
  "number": "PO-0001",
  "status": "awaiting_advance",
  "rfq_id": "c3d8a2f1-6b47-4e09-9a15-2f7e1b8d4c60",
  "rfq_number": "RFQ-0007",
  "quotation_id": "6d2f8b14-93ae-4c57-b1e0-5a7c9d3f2e81",
  "supplier_profile_id": "2c9f6a85-e7d1-4b03-9a58-4f1d8e3b6c70",
  "company_name": "Sharma Traders",
  "subtotal": "5040.00",
  "tax_total": "252.00",
  "grand_total": "5292.00",
  "advance_amount": "1000.00",
  "balance_amount": "4292.00",
  "delivery_date": "2026-10-15",
  "advance_due_by": "2026-10-14T10:00:00Z",
  "issued_at": None,
  "created_at": "2026-10-13T10:00:00Z",
}
 
PURCHASE_ORDER_NO_ADVANCE_EXAMPLE = {
  **PURCHASE_ORDER_EXAMPLE,
  "status": "issued",
  "advance_amount": "0.00",
  "balance_amount": "5292.00",
  "advance_due_by": None,
  "issued_at": "2026-10-13T10:00:00Z",
}
 
QUOTATION_NOT_FOUND_RESPONSE = resp(
  "No such quotation in this business. A quotation that belongs to another "
  "business also returns this.",
  err_example("Not Found", "Quotation not found.", "QUOTATION_NOT_FOUND"),
)
 
po_accept_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_quotations_accept",
    summary="Accept Quotation",
    description=(
      "Accepts a quotation and creates the purchase order (PO). The RFQ must be "
      "`open` or `closed` (deadline passed, nobody chosen yet); the quotation must "
      "be `submitted`, still valid (`valid_until` not passed) and cover every RFQ "
      "item at the full quantity. In one step the server creates the PO with a copy "
      "of the quotation's items, GST, totals, delivery date and advance, marks the "
      "quotation `accepted` and marks the RFQ `awarded`. From then on the supplier "
      "can no longer revise or withdraw the quotation, and no second quotation can "
      "be accepted. No supplier is notified yet and the other quotations are left "
      "as they are.\n\n"
      "If the quotation has an advance, the PO starts as `awaiting_advance` and the "
      "owner must pay the advance before `advance_due_by`. When the payment is "
      "confirmed the order becomes `issued`, the other quotations are rejected and "
      "the suppliers are told. If the advance is 0 there is nothing to pay: the "
      "order is `issued` straight away (`advance_due_by` is null) and the suppliers "
      "are told at once. `balance_amount` is the grand total minus the advance, due "
      "after delivery. No request body is needed. " + OWNER_NOTE
    ),
    request=None,
    responses={
      201: resp(
        "Quotation accepted, PO created.",
        ok_example(
          "Advance To Pay",
          "Quotation accepted. Pay the advance to confirm the order.",
          data=PURCHASE_ORDER_EXAMPLE,
        ),
        ok_example(
          "No Advance",
          "Quotation accepted and order issued.",
          data=PURCHASE_ORDER_NO_ADVANCE_EXAMPLE,
        ),
      ),
      400: resp(
        "The quotation can't be accepted.",
        err_example(
          "Quotation Expired",
          "This quotation expired on 21 Oct 2026.",
          "QUOTATION_EXPIRED",
        ),
        err_example(
          "Quotation Incomplete",
          "This quotation doesn't cover every item at the full quantity.",
          "QUOTATION_INCOMPLETE",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: QUOTATION_NOT_FOUND_RESPONSE,
      409: resp(
        "The RFQ or the quotation is no longer available.",
        err_example(
          "Already Awarded",
          "A quotation has already been accepted for this RFQ.",
          "RFQ_ALREADY_AWARDED",
        ),
        err_example("RFQ Cancelled", "This RFQ was cancelled.", "RFQ_CANCELLED"),
        err_example(
          "Quotation Not Active",
          "This quotation is no longer active.",
          "QUOTATION_NOT_ACTIVE",
        ),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)

PO_NOT_FOUND_RESPONSE = resp(
  "No such order in this business. An order that belongs to another business "
  "also returns this.",
  err_example("Not Found", "Order not found.", "ORDER_NOT_FOUND"),
)

PURCHASE_ORDER_CANCELLED_EXAMPLE = {
  **PURCHASE_ORDER_EXAMPLE,
  "status": "cancelled",
}

po_cancel_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_orders_cancel",
    summary="Cancel Unpaid Order",
    description=(
      "Cancels an order that is still `awaiting_advance`, that is, a quotation was "
      "accepted but the advance has not been paid. The order becomes `cancelled`, "
      "the quotation goes back to `submitted` and the RFQ is reopened (`open`, or "
      "`closed` if its deadline has already passed), so the owner can accept a "
      "quotation again. Suppliers are not notified because they never saw the order. "
      "An order that is already `issued` or later cannot be cancelled here, and "
      "neither can an order whose advance payment has already been received. "
      "The server also cancels unpaid orders automatically once `advance_due_by` "
      "has passed. No request body is needed. " + OWNER_NOTE
    ),
    request=None,
    responses={
      200: resp(
        "Order cancelled.",
        ok_example(
          "Cancelled",
          "Order cancelled. The quotation can be accepted again.",
          data=PURCHASE_ORDER_CANCELLED_EXAMPLE,
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: PO_NOT_FOUND_RESPONSE,
      409: resp(
        "The order can't be cancelled.",
        err_example(
          "Not Cancellable",
          "Only an order that is waiting for its advance can be cancelled.",
          "ORDER_NOT_CANCELLABLE",
        ),
        err_example(
          "Payment Received",
          "The advance has already been paid, so this order can't be cancelled here.",
          "PAYMENT_RECEIVED",
        ),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)

PO_ITEM_EXAMPLE = {
  "id": "5b8e2c71-3d94-4f06-a1c7-9e0d6b3f8a24",
  "product_id": "5d0c7e91-4b3a-4a28-8f16-c2e9a7b1d054",
  "product_name": "Amul Dahi",
  "sku": "SKU-787328",
  "image": "https://example-bucket.s3.amazonaws.com/products/dahi.jpg",
  "category": "Dairy",
  "supply_category": "Dairy",
  "quantity": 70,
  "unit_price": "42.00",
  "gst_rate": "5.00",
  "line_subtotal": "2940.00",
  "line_tax": "147.00",
  "line_total": "3087.00",
}

PURCHASE_ORDER_LIST_ITEM_EXAMPLE = {
  **PURCHASE_ORDER_NO_ADVANCE_EXAMPLE,
  "item_count": 2,
  "total_quantity": 140,
  "dispatch_date": None,
  "expected_delivery_date": "2026-10-15",
  "is_late": False,
  "late_by_days": 0,
}

PURCHASE_ORDER_DETAIL_EXAMPLE = {
  **PURCHASE_ORDER_LIST_ITEM_EXAMPLE,
  "cancelled_at": None,
  "advance_paid": False,
  "supplier": {
    "company_name": "Sharma Traders",
    "phone": "9876543210",
    "email": "sharma@example.com",
    "address": "12 Industrial Area",
    "city": "Ghaziabad",
    "gstin": "09ABCDE1234F1Z5",
  },
  "buyer": {
    "business_name": "Gupta Kirana",
    "business_type": "Retail",
    "city": "Delhi",
    "owner_name": "Ramesh Gupta",
    "email": "ramesh@example.com",
  },
  "items": [PO_ITEM_EXAMPLE],
  "shipment": None,
  "invoice": None,
}

PO_PAGE_NOT_FOUND_RESPONSE = resp(
  "The page number is out of range.",
  err_example("Invalid Page", "Invalid page.", "NOT_FOUND"),
)

PO_DETAIL_NOT_FOUND_RESPONSE = resp(
  "No such order for this user. An order that belongs to someone else also "
  "returns this.",
  err_example("Not Found", "No PurchaseOrder matches the given query.", "NOT_FOUND"),
)

PO_FIELDS_NOTE = (
  "`status` is `awaiting_advance` (accepted, advance not paid yet), `issued` (the "
  "supplier can see it), `dispatched`, `partially_received`, `received` or "
  "`cancelled`. `balance_amount` is the grand total minus the advance, due after "
  "delivery. `dispatch_date` is when the supplier dispatched the order (null until "
  "then). `expected_delivery_date` is the supplier's current expected date once "
  "dispatched, otherwise the order's `delivery_date`. `is_late` is true when the "
  "order is past its `delivery_date` before dispatch, or when the supplier set an "
  "expected date later than it at dispatch; `late_by_days` says by how many days. "
  "In the order detail, `shipment` and `invoice` are null until the order is "
  "dispatched; after that they have the same shape as in Supplier: Mark Order "
  "Dispatched."
)

po_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_orders_list",
    summary="List Orders",
    description=(
      "Returns the purchase orders of the logged-in user's business, newest first, "
      "paginated. " + PO_FIELDS_NOTE + " " + ACCESS_NOTE
    ),
    parameters=[
      OpenApiParameter(
        "status", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description=(
          "Filter by `status`. Any value that is not a status is ignored and all "
          "orders are returned."
        ),
      ),
      *PAGE_PARAMETERS,
    ],
    responses={
      200: resp(
        "Paginated order list.",
        ok_example("Orders", "Orders fetched.", data=paginated(PURCHASE_ORDER_LIST_ITEM_EXAMPLE)),
        ok_example("No Orders", "Orders fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: PO_PAGE_NOT_FOUND_RESPONSE,
    },
  ),
)

po_detail_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_orders_retrieve",
    summary="Get Order",
    description=(
      "Returns one purchase order with everything the Track Order screen needs: "
      "the `items` (each with the product `image`, `category` and `supply_category`, "
      "which are read from the product and can be null), the `supplier` contact "
      "details and the `buyer` details. `advance_paid` is true once the advance "
      "payment has been received. " + PO_FIELDS_NOTE + " " + ACCESS_NOTE
    ),
    responses={
      200: resp(
        "Order details.",
        ok_example("Order", "Order fetched.", data=PURCHASE_ORDER_DETAIL_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: PO_DETAIL_NOT_FOUND_RESPONSE,
    },
  ),
)

SUPPLIER_PO_NOTE = (
  "Supplier only. A supplier sees only their own orders, and only once an order is "
  "`issued` or later; an order that is `awaiting_advance` or `cancelled` is not listed "
  "and returns a 404."
)

supplier_po_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_orders_list",
    summary="Supplier: List My Orders",
    description=(
      "The supplier's purchase orders, newest first, paginated. "
      + PO_FIELDS_NOTE + " " + SUPPLIER_PO_NOTE
    ),
    parameters=[
      OpenApiParameter(
        "status", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description=(
          "Filter by `status`: `issued`, `dispatched`, `partially_received` or "
          "`received`. Any other value is ignored."
        ),
      ),
      *PAGE_PARAMETERS,
    ],
    responses={
      200: resp(
        "Paginated order list.",
        ok_example(
          "Orders", "Orders fetched.",
          data=paginated({
            **PURCHASE_ORDER_LIST_ITEM_EXAMPLE,
            "business_name": "Gupta Kirana",
            "business_city": "Delhi",
          }),
        ),
        ok_example("No Orders", "Orders fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: PO_PAGE_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_po_detail_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_orders_retrieve",
    summary="Supplier: Get Order",
    description=(
      "One purchase order with its items, the buyer's details and the supplier's "
      "own details. " + PO_FIELDS_NOTE + " " + SUPPLIER_PO_NOTE
    ),
    responses={
      200: resp(
        "Order details.",
        ok_example("Order", "Order fetched.", data=PURCHASE_ORDER_DETAIL_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: PO_DETAIL_NOT_FOUND_RESPONSE,
    },
  ),
)

SHIPMENT_EXAMPLE = {
  "id": "7c4e1a92-5d08-4b36-9f21-a3e8d6c0b715",
  "dispatched_at": "2026-10-14T09:30:00Z",
  "expected_delivery_date": "2026-10-17",
  "tracking_note": "Truck DL1C 4567",
  "is_late": True,
  "late_by_days": 2,
  "items": [
    {
      "purchase_order_item_id": "5b8e2c71-3d94-4f06-a1c7-9e0d6b3f8a24",
      "product_name": "Amul Dahi",
      "sku": "SKU-787328",
      "ordered_quantity": 70,
      "quantity": 70,
    },
    {
      "purchase_order_item_id": "d9a3f6b0-2e17-4c85-8b4d-1f7a0e5c9d32",
      "product_name": "Amul Milk 1L",
      "sku": "SKU-202",
      "ordered_quantity": 70,
      "quantity": 40,
    },
  ],
}

INVOICE_SUMMARY_EXAMPLE = {
  "id": "e1b7c3a5-9f02-4d68-a4e1-6c0d8b2f7a93",
  "number": "INV-0001",
  "status": "unpaid",
  "issue_date": "2026-10-14",
  "purchase_order_id": "2f6b9d04-7c1e-4a83-b5f2-9e0d3a8c6b17",
  "subtotal": "4140.00",
  "tax_total": "207.00",
  "grand_total": "4347.00",
  "advance_applied": "1000.00",
  "balance_due": "3347.00",
  "discrepancy_credit": "0.00",
  "refund_due": "0.00",
}

ORDER_NOT_FOUND_FOR_SUPPLIER_RESPONSE = resp(
  "No such order for this supplier, or the order is not `issued` or later yet.",
  err_example("Not Found", "Order not found.", "ORDER_NOT_FOUND"),
)

supplier_po_dispatch_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_supplier_orders_dispatch",
    summary="Supplier: Mark Order Dispatched",
    description=(
      "The supplier marks an `issued` order as dispatched. In one step the server "
      "creates the shipment, generates the invoice automatically and changes the "
      "order status to `dispatched`. The owner is notified, and told which products "
      "are short if less than ordered was sent. There is one shipment per order, so "
      "this can be done only once.\n\n"
      "- `items`: optional. One entry per order line, with the line's `id` from "
      "Supplier: Get Order as `purchase_order_item` and the units sent as `quantity`. "
      "The screen pre-fills the ordered quantities and the supplier may lower them, "
      "never raise them. A line with 0 or a line left out is not dispatched and not "
      "invoiced. At least one unit must be sent. If `items` is left out, everything "
      "is dispatched as ordered.\n"
      "- `expected_delivery_date`: optional, `YYYY-MM-DD`, today or later. Defaults to "
      "the order's `delivery_date`. A date later than the order's is allowed and is "
      "shown to the owner as late (`is_late`, `late_by_days`).\n"
      "- `tracking_note`: optional, up to 255 characters, for a vehicle or tracking "
      "number.\n\n"
      "The invoice is calculated by the server from the dispatched quantities, the "
      "order's unit prices and GST. `advance_applied` is the advance already paid "
      "(never more than the invoice total) and `balance_due` is what is left to pay "
      "after delivery. " + SUPPLIER_PO_NOTE + " Accepts JSON; the body may be empty."
    ),
    request=DispatchSerializer,
    examples=[
      OpenApiExample("Dispatch Everything", value={}, request_only=True),
      OpenApiExample(
        "Partial Dispatch",
        value={
          "items": [
            {"purchase_order_item": "5b8e2c71-3d94-4f06-a1c7-9e0d6b3f8a24", "quantity": 70},
            {"purchase_order_item": "d9a3f6b0-2e17-4c85-8b4d-1f7a0e5c9d32", "quantity": 40},
          ],
          "expected_delivery_date": "2026-10-17",
          "tracking_note": "Truck DL1C 4567",
        },
        request_only=True,
      ),
    ],
    responses={
      201: resp(
        "Order dispatched, invoice generated.",
        ok_example(
          "Dispatched",
          "Order marked as dispatched. Invoice generated.",
          data={"shipment": SHIPMENT_EXAMPLE, "invoice": INVOICE_SUMMARY_EXAMPLE},
        ),
      ),
      400: resp(
        "Validation error, or the quantities are not allowed.",
        err_example("Duplicate Item", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": ["Each order item can appear only once."],
        }),
        err_example("Invalid Item Id", "Validation failed.", "VALIDATION_ERROR", errors={
          "items": [{"purchase_order_item": ["Must be a valid UUID."]}],
        }),
        err_example("Invalid Date", "Validation failed.", "VALIDATION_ERROR", errors={
          "expected_delivery_date": [
            "Date has wrong format. Use one of these formats instead: YYYY-MM-DD."
          ],
        }),
        err_example(
          "Not In Order", "One of the items is not part of this order.", "INVALID_ITEM",
        ),
        err_example(
          "More Than Ordered",
          "You can't dispatch more than ordered: 70 units of Amul Milk 1L.",
          "QUANTITY_TOO_HIGH",
        ),
        err_example("Nothing Sent", "Dispatch at least one item.", "NOTHING_TO_DISPATCH"),
        err_example(
          "Date In Past",
          "The expected delivery date can't be in the past.",
          "EXPECTED_DATE_IN_PAST",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: ORDER_NOT_FOUND_FOR_SUPPLIER_RESPONSE,
      409: resp(
        "The order was already dispatched.",
        err_example(
          "Already Dispatched", "This order has already been dispatched.", "ALREADY_DISPATCHED",
        ),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)

INVOICE_LIST_ITEM_EXAMPLE = {
  **INVOICE_SUMMARY_EXAMPLE,
  "po_number": "PO-0001",
  "company_name": "Sharma Traders",
  "business_name": "Gupta Kirana",
  "item_count": 2,
}

INVOICE_DETAIL_EXAMPLE = {
  **INVOICE_LIST_ITEM_EXAMPLE,
  "created_at": "2026-10-14T09:30:00Z",
  "supplier": PURCHASE_ORDER_DETAIL_EXAMPLE["supplier"],
  "buyer": PURCHASE_ORDER_DETAIL_EXAMPLE["buyer"],
  "shipment": {
    "dispatched_at": "2026-10-14T09:30:00Z",
    "expected_delivery_date": "2026-10-17",
    "is_late": True,
    "late_by_days": 2,
    "tracking_note": "Truck DL1C 4567",
  },
  "items": [
    {
      "id": "a4c8e2d6-1b37-4f90-8d52-7e0b3a9c6f14",
      "product_name": "Amul Dahi",
      "sku": "SKU-787328",
      "quantity": 70,
      "unit_price": "42.00",
      "gst_rate": "5.00",
      "line_subtotal": "2940.00",
      "line_tax": "147.00",
      "line_total": "3087.00",
    },
    {
      "id": "3f9b5d1a-6c42-4e78-a0d3-8b2e7c4f1a65",
      "product_name": "Amul Milk 1L",
      "sku": "SKU-202",
      "quantity": 40,
      "unit_price": "30.00",
      "gst_rate": "5.00",
      "line_subtotal": "1200.00",
      "line_tax": "60.00",
      "line_total": "1260.00",
    },
  ],
}

INVOICE_AFTER_RECEIPT_EXAMPLE = {
  **INVOICE_DETAIL_EXAMPLE,
  "discrepancy_credit": "315.00",
  "balance_due": "3032.00",
  "refund_due": "0.00",
}

INVOICE_NOTE = (
  "Invoices are generated automatically when the supplier marks an order as "
  "dispatched; nobody types them. The invoice is the supplier's bill, issued to "
  "the buyer, and covers only the quantities dispatched. `advance_applied` is the "
  "advance already paid on the order and `balance_due` is what is left to pay after "
  "delivery. `status` is `unpaid` or `paid`. Numbers run per supplier (INV-0001, "
  "INV-0002, ...)."
  "`discrepancy_credit` is 0 until the buyer confirms delivery with a goods "
  "receipt. `refund_due` is the part of the advance the supplier owes back. It is "
  "set at dispatch when the advance exceeds the dispatched value, and the receipt "
  "can only increase it. The receipt recalculates `discrepancy_credit`, "
  "`balance_due` (total minus credit minus advance applied) and `refund_due`. "
)

INVOICE_NOT_FOUND_RESPONSE = resp(
  "No such invoice for this user. An invoice that belongs to someone else also "
  "returns this.",
  err_example("Not Found", "No Invoice matches the given query.", "NOT_FOUND"),
)

INVOICE_PAGE_NOT_FOUND_RESPONSE = resp(
  "The page number is out of range.",
  err_example("Invalid Page", "Invalid page.", "NOT_FOUND"),
)

STATUS_FILTER_PARAMETER = OpenApiParameter(
  "status", OpenApiTypes.STR, OpenApiParameter.QUERY,
  description="`unpaid` or `paid`. Any other value is ignored and all invoices are returned.",
)

invoice_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_invoices_list",
    summary="List Invoices",
    description=(
      "Returns the invoices issued to the logged-in user's business, newest first, "
      "paginated. " + INVOICE_NOTE + " " + ACCESS_NOTE
    ),
    parameters=[STATUS_FILTER_PARAMETER, *PAGE_PARAMETERS],
    responses={
      200: resp(
        "Paginated invoice list.",
        ok_example("Invoices", "Invoices fetched.", data=paginated(INVOICE_LIST_ITEM_EXAMPLE)),
        ok_example("No Invoices", "Invoices fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: INVOICE_PAGE_NOT_FOUND_RESPONSE,
    },
  ),
)

invoice_detail_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_invoices_retrieve",
    summary="Get Invoice",
    description=(
      "Returns one invoice with its lines, the supplier (issuer) and buyer details "
      "and the shipment dates. " + INVOICE_NOTE + " " + ACCESS_NOTE
    ),
    responses={
      200: resp(
        "Invoice details.",
        ok_example("At Dispatch", "Invoice fetched.", data=INVOICE_DETAIL_EXAMPLE),
        ok_example(
          "After Goods Receipt", "Invoice fetched.", data=INVOICE_AFTER_RECEIPT_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: INVOICE_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_invoice_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_invoices_list",
    summary="Supplier: List My Invoices",
    description=(
      "The invoices the supplier has issued, newest first, paginated. "
      + INVOICE_NOTE + " Supplier only; a supplier sees only their own invoices."
    ),
    parameters=[STATUS_FILTER_PARAMETER, *PAGE_PARAMETERS],
    responses={
      200: resp(
        "Paginated invoice list.",
        ok_example("Invoices", "Invoices fetched.", data=paginated(INVOICE_LIST_ITEM_EXAMPLE)),
        ok_example("No Invoices", "Invoices fetched.", data=paginated()),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVOICE_PAGE_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_invoice_detail_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_invoices_retrieve",
    summary="Supplier: Get Invoice",
    description=(
      "One of the supplier's invoices with its lines, both parties' details and the "
      "shipment dates. " + INVOICE_NOTE
      + " Supplier only; an invoice of another supplier returns a 404."
    ),
    responses={
      200: resp(
        "Invoice details.",
        ok_example("At Dispatch", "Invoice fetched.", data=INVOICE_DETAIL_EXAMPLE),
        ok_example(
          "After Goods Receipt", "Invoice fetched.", data=INVOICE_AFTER_RECEIPT_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVOICE_NOT_FOUND_RESPONSE,
    },
  ),
)


GATEWAY_ERROR_RESPONSE = resp(
  "Razorpay could not be reached or returned an error. Safe to retry.",
  err_example(
    "Gateway Error",
    "Couldn't reach the payment gateway. Try again in a minute.",
    "GATEWAY_ERROR",
  ),
)

PAYMENTS_OFF_RESPONSE = resp(
  "Razorpay keys are not configured on the server.",
  err_example(
    "Not Configured",
    "Online payments aren't set up yet.",
    "PAYMENTS_NOT_CONFIGURED",
  ),
)

PAYMENT_EXAMPLE = {
  "id": "8a1c4e72-5d3b-4f96-a0e8-7b2d9c6f1e35",
  "amount": "1000.00",
  "status": "created",
  "razorpay_order_id": "order_PZ3k8sQm1vXy2a",
  "razorpay_payment_id": None,
  "failure_reason": "",
  "refund_id": "",
  "paid_at": None,
  "created_at": "2026-10-13T10:02:00Z",
}

PAYMENT_PAID_EXAMPLE = {
  **PAYMENT_EXAMPLE,
  "status": "paid",
  "razorpay_payment_id": "pay_PZ3lQw7tN4bR9c",
  "paid_at": "2026-10-13T10:05:00Z",
}

PURCHASE_ORDER_ISSUED_EXAMPLE = {
  **PURCHASE_ORDER_EXAMPLE,
  "status": "issued",
  "issued_at": "2026-10-13T10:05:00Z",
}

CHECKOUT_EXAMPLE = {
  "key": "rzp_test_1DP5mmOlF5G5ag",
  "order_id": "order_PZ3k8sQm1vXy2a",
  "amount": 100000,
  "currency": "INR",
  "name": "Kosh",
  "description": "Advance for PO-0001 - Sharma Traders",
  "prefill": {"name": "Ravi Kumar", "email": "ravi@example.com"},
  "notes": {"purchase_order_id": "2f6b9d04-7c1e-4a83-b5f2-9e0d3a8c6b17"},
  "purchase_order_id": "2f6b9d04-7c1e-4a83-b5f2-9e0d3a8c6b17",
  "advance_due_by": "2026-10-14T10:00:00Z",
}

ADVANCE_STATE_CONFLICT = (
  err_example(
    "Already Paid",
    "The advance for this order is already paid.",
    "ADVANCE_ALREADY_PAID",
  ),
  err_example("Order Cancelled", "This order was cancelled.", "ORDER_CANCELLED"),
  err_example(
    "Advance Expired",
    "The time to pay this advance has run out.",
    "ADVANCE_EXPIRED",
  ),
  err_example("No Advance", "This order has no advance to pay.", "NO_ADVANCE_DUE"),
)

po_advance_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_purchase_orders_advance_status",
    summary="Advance Payment Status",
    description=(
      "Returns the purchase order and every payment attempt made for its advance, "
      "newest first. Use it to refresh the screen after Checkout closes, or to show "
      "the payment history. Payment `status` is `created` (Razorpay order open, not "
      "paid yet), `paid`, `failed` (advance expired before payment) or `refunded` "
      "(money arrived after the order was closed and was sent back; see `refund_id`). "
      "`failure_reason` holds Razorpay's message for the last failed attempt. "
      + OWNER_NOTE
    ),
    responses={
      200: resp(
        "Advance status.",
        ok_example(
          "Awaiting Payment",
          "Advance status.",
          data={"order": PURCHASE_ORDER_EXAMPLE, "payments": [PAYMENT_EXAMPLE]},
        ),
        ok_example(
          "Paid",
          "Advance status.",
          data={
            "order": PURCHASE_ORDER_ISSUED_EXAMPLE,
            "payments": [PAYMENT_PAID_EXAMPLE],
          },
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: PO_NOT_FOUND_RESPONSE,
    },
  ),
  post=extend_schema(
    operation_id="procurement_purchase_orders_advance_start",
    summary="Start Advance Payment",
    description=(
      "Creates a Razorpay order for the PO's advance and returns everything the "
      "frontend passes to Razorpay Checkout (`key`, `order_id`, `amount`, `currency`, "
      "`name`, `description`, `prefill`, `notes`). `amount` is in **paise** "
      "(₹1000.00 = 100000). Calling it again while the advance is unpaid returns the "
      "same `order_id`, so a double click or a retry never creates a second order.\n\n"
      "The PO must be `awaiting_advance` and `advance_due_by` must not have passed. "
      "After the owner pays, call **Verify Advance Payment** with the three "
      "`razorpay_*` values from Checkout's success handler. If that call is lost, "
      "Razorpay's webhook confirms the payment anyway. No request body is needed. "
      + OWNER_NOTE
    ),
    request=None,
    responses={
      200: resp("Checkout ready.", ok_example("Checkout Ready", "Checkout ready.", data=CHECKOUT_EXAMPLE)),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: PO_NOT_FOUND_RESPONSE,
      409: resp("The advance can't be paid now.", *ADVANCE_STATE_CONFLICT),
      429: THROTTLED_RESPONSE,
      502: GATEWAY_ERROR_RESPONSE,
      503: PAYMENTS_OFF_RESPONSE,
    },
  ),
)

po_advance_verify_docs = extend_schema_view(
  post=extend_schema(
    operation_id="procurement_purchase_orders_advance_verify",
    summary="Verify Advance Payment",
    description=(
      "Call this from Razorpay Checkout's success `handler` with the three values it "
      "returns. The server checks the signature, fetches the payment from Razorpay, "
      "captures it if it is only authorized, and checks the amount. The payment then "
      "becomes `paid` and the PO becomes `issued`; the other quotations are rejected "
      "and the supplier is notified.\n\n"
      "Safe to call more than once: if the webhook already confirmed the payment, "
      "the same result is returned. If the money arrived after the order was "
      "cancelled, the response is still 200 but the PO stays `cancelled` and the "
      "payment is refunded automatically. " + OWNER_NOTE
    ),
    request=AdvanceVerifySerializer,
    examples=[
      OpenApiExample(
        "Checkout Response",
        value={
          "razorpay_order_id": "order_PZ3k8sQm1vXy2a",
          "razorpay_payment_id": "pay_PZ3lQw7tN4bR9c",
          "razorpay_signature": "9ef4dffbfd84f1318f6739a3ce19f9d85851857ae648f114332d8401e0949a3d",
        },
        request_only=True,
      ),
    ],
    responses={
      200: resp(
        "Payment confirmed.",
        ok_example(
          "Order Issued",
          "Advance paid. The order has been sent to the supplier.",
          data=PURCHASE_ORDER_ISSUED_EXAMPLE,
        ),
        ok_example(
          "Late Payment Refunded",
          "Payment received, but this order was already closed. It will be refunded.",
          data={**PURCHASE_ORDER_EXAMPLE, "status": "cancelled"},
        ),
      ),
      400: resp(
        "The payment could not be verified.",
        err_example(
          "Validation Error",
          "Validation failed.",
          "VALIDATION_ERROR",
          errors={"razorpay_signature": ["This field is required."]},
        ),
        err_example("Bad Signature", "We couldn't verify this payment.", "INVALID_SIGNATURE"),
        err_example(
          "Wrong Order",
          "This payment belongs to a different order.",
          "ORDER_MISMATCH",
        ),
        err_example(
          "Amount Mismatch",
          "The paid amount doesn't match the advance.",
          "AMOUNT_MISMATCH",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: resp(
        "No payment with this `razorpay_order_id` on this PO in this business.",
        err_example("Not Found", "Payment not found.", "PAYMENT_NOT_FOUND"),
      ),
      409: resp(
        "Razorpay hasn't completed the payment yet.",
        err_example(
          "Not Captured",
          "This payment isn't complete yet.",
          "PAYMENT_NOT_CAPTURED",
        ),
      ),
      429: THROTTLED_RESPONSE,
      502: GATEWAY_ERROR_RESPONSE,
      503: PAYMENTS_OFF_RESPONSE,
    },
  ),
)
