from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from accounts.swagger import THROTTLED_EXAMPLE, UNAUTHORIZED_RESPONSE, err_example, ok_example, resp

SEARCH_NOTE = (
  "Searches the caller's business only (owner and employee). Returns up to 5 results "
  "per type, grouped. Each result has `id`, `type`, `title` and `subtitle`; the frontend "
  "decides which page a `type` opens. Matches are case-insensitive and can be anywhere "
  "in the text, with results that start with the term listed first. "
  "A query shorter than 3 characters returns empty groups (no database work). "
  "Searched: products (name, SKU; active only), suppliers (email, label, company name), "
  "RFQs (number, supply category), purchase orders and invoices (number, supplier "
  "company name), goods receipts (number, PO number)."
)

SEARCH_EXAMPLE = {
  "products": [
    {"id": "5b1f0c7e-2a64-4d93-8e10-7c3a9d2f6b48", "type": "product",
     "title": "Tata Salt 1kg", "subtitle": "SKU-101 · In Stock (120)"},
  ],
  "suppliers": [
    {"id": "9d3e6a1b-4c52-4f80-b7a9-1e8c5d0f3a26", "type": "supplier",
     "title": "Tata Consumer Distributors", "subtitle": "sales@tatadist.example"},
  ],
  "rfqs": [],
  "purchase_orders": [
    {"id": "2f6b9d04-7c1e-4a83-b5f2-9e0d3a8c6b17", "type": "purchase_order",
     "title": "PO-0001", "subtitle": "Tata Consumer Distributors · Issued"},
  ],
  "invoices": [],
  "goods_receipts": [],
}

EMPTY_EXAMPLE = {key: [] for key in SEARCH_EXAMPLE}

global_search_docs = extend_schema_view(
  get=extend_schema(
    tags=["Search"],
    operation_id="search_global",
    summary="Global Search",
    description=SEARCH_NOTE,
    parameters=[
      OpenApiParameter(
        "q", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description="Search text. At least 3 characters, up to 50.",
      ),
    ],
    responses={
      200: resp(
        "Grouped search results.",
        ok_example("Matches Found", "Search results fetched.", data=SEARCH_EXAMPLE),
        ok_example("Too Short Or No Match", "Search results fetched.", data=EMPTY_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: resp(
        "The user has no business yet.",
        err_example(
          "No Business",
          "Register your business or join one before using this feature.",
          "PERMISSION_DENIED",
        ),
      ),
      429: resp( "Too many searches in a minute", THROTTLED_EXAMPLE)
    },
  ),
)
