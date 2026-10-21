from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema

from accounts.swagger import (
  THROTTLED_EXAMPLE,
  UNAUTHORIZED_RESPONSE,
  err_example,
  ok_example,
  resp,
)

from .serializers import GoodsReceiptCreateSerializer

TAGS = ["Goods receipts"]

SETTLEMENT = {
  "id": "0b8e3c52-6f0e-4a57-9d3e-2f6f8b1f7a10",
  "number": "INV-0007",
  "status": "unpaid",
  "grand_total": "37800.00",
  "discrepancy_credit": "2100.00",
  "advance_applied": "10000.00",
  "balance_due": "25700.00",
  "refund_due": "0.00",
}

ITEM = {
  "id": "7d2f4b1e-8c39-4d0a-b1a5-3e6c9a52f001",
  "purchase_order_item": "c41a9e62-5b7d-4f08-a3d1-90be7c12d003",
  "product_name": "Basmati Rice 5kg",
  "sku": "RICE-5KG",
  "ordered_quantity": 100,
  "dispatched_quantity": 90,
  "received_quantity": 88,
  "rejected_quantity": 3,
  "accepted_quantity": 85,
  "credit_amount": "2100.00",
  "note": "Three bags torn",
  "discrepancies": [
    {"kind": "short_shipped", "kind_label": "Shipped less than ordered", "quantity": 10},
    {"kind": "short_received", "kind_label": "Received less than shipped", "quantity": 2},
    {"kind": "rejected", "kind_label": "Rejected or damaged", "quantity": 3},
  ],
}

LIST_ROW = {
  "id": "5f1c0a7e-2d84-4b96-8e3a-1c7d5e9b2a40",
  "number": "GRN-0001",
  "purchase_order_id": "e90b6d13-7a52-4c8f-b2d4-6f1a3c8e7b55",
  "purchase_order_number": "PO-0007",
  "supplier_name": "Sharma Traders",
  "business_name": "Kosh Mart",
  "received_at": "2026-10-22T10:15:00Z",
  "discrepancy_count": 3,
  "settlement": SETTLEMENT,
}

DETAIL = {
  **LIST_ROW,
  "notes": "Driver arrived late, bags were stacked wet.",
  "received_by": "Aman Verma",
  "items": [ITEM],
}

PAGINATED = {
  "count": 1,
  "next": None,
  "previous": None,
  "results": [LIST_ROW],
}

NOT_FOUND = resp(
  "Order or receipt not found (or it belongs to another business).",
  err_example("Not found", "Order not found.", "ORDER_NOT_FOUND"),
)

RECEIVE_REQUEST = OpenApiExample(
  "Delivery with issues",
  value={
    "items": [
      {
        "purchase_order_item": "c41a9e62-5b7d-4f08-a3d1-90be7c12d003",
        "received_quantity": 88,
        "rejected_quantity": 3,
        "note": "Three bags torn",
      }
    ],
    "notes": "Driver arrived late, bags were stacked wet.",
  },
  request_only=True,
)


grn_create_docs = extend_schema(
  tags=TAGS,
  summary="Confirm delivery of an order (create the goods receipt)",
  description=(
    "Records what physically arrived for a **dispatched** order. Available to the "
    "owner and employees.\n\n"
    "Send one line for every item the supplier dispatched. `received_quantity` is "
    "what arrived; `rejected_quantity` is the part of it that is damaged or unusable "
    "(it can't exceed received). Items the supplier didn't dispatch can be left out.\n\n"
    "In one transaction this:\n"
    "- stores the receipt and works out discrepancies automatically "
    "(`short_shipped`, `short_received`, `rejected`, `excess`)\n"
    "- adds the accepted quantity (received minus rejected) to warehouse stock\n"
    "- credits the invoice for anything dispatched but not accepted and recalculates "
    "`balance_due` / `refund_due`\n"
    "- marks the order `received`, closes the linked reorder alerts and raises new "
    "ones for products still below their reorder point\n\n"
    "A receipt can only be created once per order and can't be edited afterwards."
  ),
  request=GoodsReceiptCreateSerializer,
  examples=[RECEIVE_REQUEST],
  responses={
    201: resp(
      "Goods receipt created.",
      ok_example(
        "Received with issues",
        "Goods received. Stock updated and the invoice settled.",
        DETAIL,
      ),
    ),
    400: resp(
      "Invalid quantities.",
      err_example(
        "Missing items",
        "Enter the received quantity for every dispatched item: Basmati Rice 5kg.",
        "MISSING_ITEMS",
      ),
      err_example(
        "Rejected too high",
        "Rejected can't be more than received for Basmati Rice 5kg.",
        "REJECTED_TOO_HIGH",
      ),
      err_example(
        "Nothing received",
        "Nothing was received. If the delivery hasn't arrived, don't confirm it yet.",
        "NOTHING_RECEIVED",
      ),
      err_example(
        "Item not on the order",
        "One of the items is not part of this order.",
        "INVALID_ITEM",
      ),
    ),
    401: UNAUTHORIZED_RESPONSE,
    404: NOT_FOUND,
    409: resp(
      "The order is not in a state that can be received.",
      err_example(
        "Not dispatched",
        "This order hasn't been dispatched yet.",
        "ORDER_NOT_DISPATCHED",
      ),
      err_example(
        "Already received",
        "Goods for this order were already received.",
        "ALREADY_RECEIVED",
      ),
    ),
    429: resp("Too many requests.", THROTTLED_EXAMPLE),
  },
)

_has_discrepancies_param = OpenApiParameter(
  name="has_discrepancies",
  type=bool,
  location=OpenApiParameter.QUERY,
  required=False,
  description="Pass `true` to list only receipts that recorded at least one discrepancy.",
)

grn_list_docs = extend_schema(
  tags=TAGS,
  summary="List goods receipts",
  description="Receipts for the caller's business, newest first, with the invoice settlement.",
  parameters=[_has_discrepancies_param],
  responses={
    200: resp("Paginated receipts.", ok_example("Receipts", "Goods receipts fetched.", PAGINATED)),
    401: UNAUTHORIZED_RESPONSE,
  },
)

grn_detail_docs = extend_schema(
  tags=TAGS,
  summary="Get a goods receipt",
  description=(
    "One receipt with its lines, per-line discrepancies, credit amounts and the "
    "resulting invoice settlement."
  ),
  responses={
    200: resp("Receipt.", ok_example("Receipt", "Goods receipt fetched.", DETAIL)),
    401: UNAUTHORIZED_RESPONSE,
    404: resp(
      "Receipt not found.",
      err_example("Not found", "Not found.", "NOT_FOUND"),
    ),
  },
)

supplier_grn_list_docs = extend_schema(
  tags=TAGS,
  summary="List goods receipts for my orders (supplier)",
  description="Receipts raised against the supplier's own orders, newest first.",
  parameters=[_has_discrepancies_param],
  responses={
    200: resp("Paginated receipts.", ok_example("Receipts", "Goods receipts fetched.", PAGINATED)),
    401: UNAUTHORIZED_RESPONSE,
  },
)

_supplier_detail = {**DETAIL, "received_by": None}

supplier_grn_detail_docs = extend_schema(
  tags=TAGS,
  summary="Get a goods receipt for my order (supplier)",
  description=(
    "Same shape as the business view, except `received_by` is always null: "
    "supplier accounts don't see the buyer's staff names."
  ),
  responses={
    200: resp(
      "Receipt.", ok_example("Receipt", "Goods receipt fetched.", _supplier_detail)
    ),
    401: UNAUTHORIZED_RESPONSE,
    404: resp(
      "Receipt not found.",
      err_example("Not found", "Not found.", "NOT_FOUND"),
    ),
  },
)
