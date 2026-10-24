from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from accounts.swagger import UNAUTHORIZED_RESPONSE, err_example, ok_example, resp

from .SwaggerDocs import (
  INVITATION_ID,
  NOT_SUPPLIER_RESPONSE,
  PAGE_PARAMETERS,
  QUOTATION_EXAMPLE,
)

PO_ID = "2f6b9d04-7c1e-4a83-b5f2-9e0d3a8c6b17"


def page(*results):
  return {"count": len(results), "next": None, "previous": None, "results": list(results)}


QUOTATION_STATUS_ACCEPTED_EXAMPLE = {
  "id": QUOTATION_EXAMPLE["id"],
  "invitation_id": INVITATION_ID,
  "rfq_id": "c3d8a2f1-6b47-4e09-9a15-2f7e1b8d4c60",
  "rfq_number": "RFQ-7568",
  "revision": 1,
  "business_name": "Gupta Kirana",
  "business_city": "Delhi",
  "status": "accepted",
  "advance_status": "paid",
  "order_id": PO_ID,
  "order_number": "PO-0001",
  "order_status": "issued",
  "total_quantity": 140,
  "grand_total": "5292.00",
  "advance_amount": "1000.00",
  "delivery_date": "2026-10-15",
  "submitted_at": "2026-10-13T12:50:00Z",
  "updated_at": "2026-10-14T08:10:00Z",
}

QUOTATION_STATUS_PENDING_EXAMPLE = {
  "id": "b8e4d2a6-5c13-4f79-8a0e-1d7c3b9f6e24",
  "invitation_id": "a2c7e9b1-3d58-4046-b6f0-8e1a5c4d7b92",
  "rfq_id": "d5f1b8c3-7e29-4a60-9c14-0b6a2e8d5f37",
  "rfq_number": "RFQ-7571",
  "revision": 2,
  "business_name": "Verma General Store",
  "business_city": "Noida",
  "status": "submitted",
  "advance_status": "pending",
  "order_id": None,
  "order_number": None,
  "order_status": None,
  "total_quantity": 60,
  "grand_total": "3150.00",
  "advance_amount": "500.00",
  "delivery_date": "2026-10-20",
  "submitted_at": "2026-10-14T09:05:00Z",
  "updated_at": "2026-10-14T11:40:00Z",
}

QUOTATION_STATUS_NO_ADVANCE_EXAMPLE = {
  "id": "e7a3c5f9-1b64-4d82-a0c7-5f9e2b8d4a16",
  "invitation_id": "f3b8d1e6-9a25-4c70-8e43-2d6a0c7b5f81",
  "rfq_id": "9a4e7c2d-6f18-4b53-a1d9-8c3e5b0f7a62",
  "rfq_number": "RFQ-7560",
  "revision": 1,
  "business_name": "Singh Mart",
  "business_city": "Ghaziabad",
  "status": "accepted",
  "advance_status": "not_required",
  "order_id": "7c1e4a93-2b60-4d58-9e07-3a8f6d2c1b45",
  "order_number": "PO-0002",
  "order_status": "dispatched",
  "total_quantity": 200,
  "grand_total": "8400.00",
  "advance_amount": "0.00",
  "delivery_date": "2026-10-12",
  "submitted_at": "2026-10-09T10:20:00Z",
  "updated_at": "2026-10-11T15:30:00Z",
}

QUOTATION_STATUS_REJECTED_EXAMPLE = {
  "id": "3d9c6a1f-8e47-4b25-b0a8-6e2f4c7d9b13",
  "invitation_id": "6e1b9f4a-2c73-4d80-a5e6-9b0d8c3f2a74",
  "rfq_id": "1b7d4e9a-5c30-4f62-8a1e-7d3c9b6f0e28",
  "rfq_number": "RFQ-7549",
  "revision": 1,
  "business_name": "Kapoor Provisions",
  "business_city": "Delhi",
  "status": "rejected",
  "advance_status": None,
  "order_id": None,
  "order_number": None,
  "order_status": None,
  "total_quantity": 90,
  "grand_total": "4725.00",
  "advance_amount": "0.00",
  "delivery_date": "2026-10-08",
  "submitted_at": "2026-10-05T08:45:00Z",
  "updated_at": "2026-10-07T12:00:00Z",
}

QUOTATION_STATUS_WITHDRAWN_EXAMPLE = {
  "id": "9f2a5d8c-4b71-4e36-a9c0-1d7e3b6f8a52",
  "invitation_id": "c9d2a7e5-1f48-4b63-8d0a-5e3b7c1f9a26",
  "rfq_id": "5e8a1d4b-9c27-4f03-b6a5-2c7f0e9d3b81",
  "rfq_number": "RFQ-7544",
  "revision": 1,
  "business_name": "Gupta Kirana",
  "business_city": "Delhi",
  "status": "withdrawn",
  "advance_status": None,
  "order_id": None,
  "order_number": None,
  "order_status": None,
  "total_quantity": 40,
  "grand_total": "1680.00",
  "advance_amount": "0.00",
  "delivery_date": "2026-10-06",
  "submitted_at": "2026-10-03T13:10:00Z",
  "updated_at": "2026-10-04T09:25:00Z",
}

QUOTATION_STATUS_NOTE = (
  "One row per quotation the supplier has posted, for the Quotation Status cards. "
  "Newest activity first, paginated. Withdrawn and rejected quotations are included; "
  "filter by `status` to hide them. "
  "`status` is `submitted` (waiting for the buyer), `accepted`, `rejected` or "
  "`withdrawn`. A quotation the buyer has accepted still shows as `submitted` until "
  "the order is confirmed (its advance is paid, or no advance was required), so a "
  "supplier never learns about an order that may still be cancelled. "
  "`advance_status` drives the Paid/Pending badge: `pending` while the quotation is "
  "waiting for the buyer, then `paid` once the order is issued, or `not_required` "
  "when `advance_amount` is 0. It is null for `rejected` and `withdrawn`, so the "
  "card can show a dash. "
  "`order_id`, `order_number` and `order_status` are null until the order is issued; "
  "after that `order_status` follows the order (`issued`, `dispatched`, "
  "`partially_received`, `received`). "
  "`total_quantity` is the number of units across all items (the card's stock). "
  "`grand_total` includes GST. "
  "`id` is the quotation id. To open a quotation or its RFQ, use `invitation_id` "
  "with the existing supplier endpoints (for example "
  "`GET /supplier/rfqs/<invitation_id>/quotation/`); they don't take the quotation "
  "id or the RFQ id. "
  "Supplier only; a supplier sees only their own quotations."
)

supplier_quotation_status_list_docs = extend_schema_view(
  get=extend_schema(
    operation_id="procurement_supplier_quotations_list",
    summary="Supplier: List My Quotations",
    description=QUOTATION_STATUS_NOTE,
    parameters=[
      OpenApiParameter(
        "status", OpenApiTypes.STR, OpenApiParameter.QUERY,
        enum=["submitted", "accepted", "rejected", "withdrawn"],
        description=(
          "Filter by the `status` shown on the card. `submitted` also includes "
          "quotations that are accepted but whose order isn't confirmed yet. Any "
          "other value is ignored and all quotations are returned."
        ),
      ),
      OpenApiParameter(
        "search", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description=(
          "Case-insensitive match on the RFQ number, the buyer's business name or "
          "the order number (confirmed orders only). Up to 100 characters."
        ),
      ),
      *PAGE_PARAMETERS,
    ],
    responses={
      200: resp(
        "Paginated quotation list.",
        ok_example(
          "Mixed Statuses",
          "Quotations fetched.",
          data=page(
            QUOTATION_STATUS_ACCEPTED_EXAMPLE,
            QUOTATION_STATUS_PENDING_EXAMPLE,
            QUOTATION_STATUS_NO_ADVANCE_EXAMPLE,
            QUOTATION_STATUS_REJECTED_EXAMPLE,
            QUOTATION_STATUS_WITHDRAWN_EXAMPLE,
          ),
        ),
        ok_example("No Quotations", "Quotations fetched.", data=page()),
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
