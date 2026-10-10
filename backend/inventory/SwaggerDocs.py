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

from .serializers import (
  QUANTITY_ERROR,
  CategorySerializer,
  ProductSerializer,
  StockAdjustmentSerializer,
  WarehouseSerializer,
  DispatchCreateSerializer,
  DispatchNoteSerializer,
  OutletSerializer,
)


PRODUCT_ID = "7d1c1e0a-5b52-4a8e-9a43-3c2f5d3a9b10"
CATEGORY_ID = "2b6f0c9e-1d3a-4f7e-8a21-5c9d7e4b3a10"
WAREHOUSE_ID = "9a4e7d52-3c18-4b6f-a0d5-1e2f8c6b7d93"

PRODUCT_EXAMPLE = {
  "id": PRODUCT_ID,
  "name": "Parle-G Biscuits 200g",
  "image": "https://example-bucket.s3.amazonaws.com/products/parleg-200.jpg",
  "sku": "PARLEG-200",
  "description": "Glucose biscuits, 200 g pack",
  "category": CATEGORY_ID,
  "category_name": "Biscuits and Snacks",
  "warehouse": WAREHOUSE_ID,
  "warehouse_name": "Main Godown",
  "price": "20.00",
  "cost_price": "16.50",
  "quantity": 120,
  "low_stock_threshold": 10,
  "status": "In Stock",
  "is_active": True,
  "created_at": "2026-10-05T10:00:00Z",
  "updated_at": "2026-10-05T10:00:00Z",
}

CATEGORY_EXAMPLE = {
  "id": CATEGORY_ID,
  "name": "Biscuits and Snacks",
  "created_at": "2026-10-05T10:00:00Z",
  "updated_at": "2026-10-05T10:00:00Z",
}

WAREHOUSE_EXAMPLE = {
  "id": WAREHOUSE_ID,
  "name": "Main Godown",
  "address": "Plot 12, Industrial Area, Ghaziabad 201001",
  "created_at": "2026-10-05T10:00:00Z",
  "updated_at": "2026-10-05T10:00:00Z",
}


NO_BUSINESS_EXAMPLE = err_example(
  "No Business",
  "Register your business or join one before using this feature.",
  "FORBIDDEN",
)

FORBIDDEN_RESPONSE = resp(
  "The user neither owns nor works for a business.",
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


def not_found(label):
  return resp(
    f"No such {label.lower()} in this business.",
    err_example("Not Found", f"No {label} matches the given query.", "NOT_FOUND"),
  )


def validation(errors):
  return resp(
    "Validation error.",
    err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR", errors=errors),
  )

def validation_cases(*cases):
  return resp(
    "Validation error.",
    *[
      err_example(name, "Validation failed.", "VALIDATION_ERROR", errors=errors)
      for name, errors in cases
    ],
  )

PRODUCT_BODY_NOTE = (
  "Accepts both `application/json` and `multipart/form-data`. Use JSON for normal "
  "product data, and use `multipart/form-data` when uploading or replacing the "
  "`image` file. `category` must be an id from this business; send it empty to "
  "clear it. `warehouse` is read-only: the server always puts products in the "
  "business's one warehouse."
)

QUANTITY_NOTE = (
  "`Quantity` is read-only: sending it on create or update returns a 400." 
  "Set starting stock with opening_quantity when creating a product (create only, 0 to 1,000,000), then change stock with the adjust-stock endpoint."
)

OWNER_NOTE = "Owner only; employees get a 403."


PRODUCT_LIST_PARAMS = [
  OpenApiParameter(
    "search", OpenApiTypes.STR, OpenApiParameter.QUERY,
    description="Matches part of the product name, ignoring upper and lower case.",
  ),
  OpenApiParameter(
    "category", OpenApiTypes.UUID, OpenApiParameter.QUERY,
    description="Only products in this category id.",
  ),
  OpenApiParameter(
    "ordering", OpenApiTypes.STR, OpenApiParameter.QUERY,
    description=(
      "Comma-separated sort fields: `name`, `price`, `created_at`, `updated_at`. "
      "Prefix a field with `-` for descending, for example `-price,name`. "
      "If any field is not allowed, the whole parameter is ignored."
    ),
  ),
  OpenApiParameter(
    "page", OpenApiTypes.INT, OpenApiParameter.QUERY,
    description="Page number, starting at 1.",
  ),
  OpenApiParameter(
    "page_size", OpenApiTypes.INT, OpenApiParameter.QUERY,
    description="Products per page. Default 10, maximum 50.",
  ),
]

PRODUCT_PAGE_RESPONSE = resp(
  "One page of products.",
  ok_example(
    "Product page",
    "Product list fetched.",
    data={
      "count": 25,
      "next": "https://kosh.dev-sushant.me/inventory/products/?page=2",
      "previous": None,
      "results": [PRODUCT_EXAMPLE],
    },
  ),
)

PRODUCT_WRITE_EXAMPLE = {
  "name": "Parle-G Biscuits 200g",
  "sku": "PARLEG-200",
  "description": "Glucose biscuits, 200 g pack",
  "price": "20.00",
  "cost_price": "16.50",
  "opening_quantity": 50,
  "low_stock_threshold": 10,
  "category": CATEGORY_ID,
}

QUANTITY_NOT_ALLOWED = ("Quantity Not Allowed", {"quantity": [QUANTITY_ERROR]})

product_list_create_docs = extend_schema_view(
  get=extend_schema(
    operation_id="inventory_products_list",
    summary="List Products",
    description=(
      "Returns a page of the logged-in user's business products, with optional "
      "search, filters and sorting. Results are paginated."
    ),
    parameters=PRODUCT_LIST_PARAMS,
    responses={
      200: PRODUCT_PAGE_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
  post=extend_schema(
    summary="Create Product",
    description=(
      "Creates a product in the logged-in user's business. The business is set by "
      "the server, never by the request body. The `sku` is trimmed, stored in upper "
      "case and must be unique within the business. "
      + QUANTITY_NOTE + " " + OWNER_NOTE + " " + PRODUCT_BODY_NOTE
    ),
    request=ProductSerializer,
    examples=[
      OpenApiExample("Full Product", value=PRODUCT_WRITE_EXAMPLE, request_only=True),
      OpenApiExample(
        "Required Fields Only",
        value={"name": "Parle-G Biscuits 200g", "sku": "PARLEG-200", "price": "20.00"},
        request_only=True,
      ),
    ],
    responses={
      201: resp("Product created.",
                ok_example("Created", "Product created.", data=PRODUCT_EXAMPLE)),
      400: validation_cases(
        ("Missing Fields", {
          "name": ["This field is required."],
          "sku": ["This field is required."],
          "price": ["This field is required."],
        }),
        ("Duplicate SKU", {"sku": ["SKU already exists in your inventory."]}),
        ("Unknown Category", {
          "category": [f'Invalid pk "{CATEGORY_ID}" - object does not exist.'],
        }),
        QUANTITY_NOT_ALLOWED,
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

product_detail_docs = extend_schema_view(
  get=extend_schema(
    summary="Get Product",
    responses={
      200: resp("Product details.",
                ok_example("Product", "Product fetched.", data=PRODUCT_EXAMPLE)),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
  put=extend_schema(
    summary="Replace Product",
    description=(
      "Full update. `name`, `sku` and `price` are required. "
      + QUANTITY_NOTE + " " + OWNER_NOTE + " " + PRODUCT_BODY_NOTE
    ),
    request=ProductSerializer,
    examples=[
      OpenApiExample("Replace Product", value=PRODUCT_WRITE_EXAMPLE, request_only=True),
    ],
    responses={
      200: resp("Product updated.",
                ok_example("Updated", "Product updated.", data=PRODUCT_EXAMPLE)),
      400: validation_cases(
        ("Missing Fields", {"sku": ["This field is required."]}),
        ("Duplicate SKU", {"sku": ["SKU already exists in your inventory."]}),
        ("Opening Quantity Not Allowed", {"opening_quantity": ["Opening stock can only be set when creating a product."]}),
        QUANTITY_NOT_ALLOWED,
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
  patch=extend_schema(
    summary="Update Product",
    description=(
      "Partial update. Send only the fields you want to change. "
      + QUANTITY_NOTE + " " + OWNER_NOTE + " " + PRODUCT_BODY_NOTE
    ),
    request=ProductSerializer,
    examples=[
      OpenApiExample("Change Price", value={"price": "25.00"}, request_only=True),
      OpenApiExample("Deactivate Product", value={"is_active": False}, request_only=True),
    ],
    responses={
      200: resp("Product updated.",
                ok_example("Updated", "Product updated.", data=PRODUCT_EXAMPLE)),
      400: validation_cases(
        ("Invalid Price", {"price": ["A valid number is required."]}),
        ("Duplicate SKU", {"sku": ["SKU already exists in your inventory."]}),
        ("Opening Quantity Not Allowed", {"opening_quantity": ["Opening stock can only be set when creating a product."]}),
        QUANTITY_NOT_ALLOWED,
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
  delete=extend_schema(
    summary="Delete Product",
    description=(
      "Permanently deletes the product. To keep it but hide it, set `is_active` "
      "to false instead. This also deletes the product stock history." + OWNER_NOTE
    ),
    responses={
      200: resp("Product deleted.", ok_example("Deleted", "Product deleted.")),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
)

product_adjust_stock_docs = extend_schema_view(
  post=extend_schema(
    summary="Adjust Product Stock",
    description=(
      "Corrects a product's stock up or down. `change` is a whole number between "
      "-1,000,000 and 1,000,000 and cannot be zero: positive adds stock, negative "
      "removes it. `reason` is either `adjustment` (default: counting errors, found "
      "stock) or `damaged` (stock lost to damage; `change` must then be negative). "
      "`note` is an optional free-text explanation (up to 255 characters). Each call "
      "adds one entry to the stock ledger with the chosen reason and note. The product "
      "row is locked while the change is applied, so simultaneous adjustments can't "
      "clash. If the result would be below zero, nothing changes and a 400 is returned. "
      "Do not use this to send stock to an outlet: record a dispatch instead, because "
      "only dispatches count as demand for reordering. Both the owner and employees "
      "can adjust stock. Accepts JSON."
    ),
    request=StockAdjustmentSerializer,
    examples=[
      OpenApiExample(
        "Add Stock",
        value={"change": 50, "reason": "adjustment", "note": "Found 50 in back store"},
        request_only=True,
      ),
      OpenApiExample(
        "Remove Stock",
        value={"change": -5, "reason": "adjustment", "note": "Count correction"},
        request_only=True,
      ),
      OpenApiExample(
        "Damaged Stock",
        value={"change": -3, "reason": "damaged", "note": "Water damage"},
        request_only=True,
      ),
      OpenApiExample("Minimal", value={"change": -5}, request_only=True),
    ],
    responses={
      200: resp("Stock updated. Returns the full product.",
                ok_example("Stock Updated", "Stock updated.",
                           data={**PRODUCT_EXAMPLE, "quantity": 170})),
      400: validation_cases(
        ("Insufficient Stock", {"change": ["Insufficient stock for Parle-G Biscuits 200g."]}),
        ("Zero Change", {"change": ["Change cannot be zero."]}),
        ("Invalid Change", {"change": ["A valid integer is required."]}),
        ("Invalid Reason", {"reason": ['"sold" is not a valid choice.']}),
        ("Damaged Must Be Negative",
         {"change": ["Damaged stock must be a negative change."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
)

def name_only_crud_docs(label, plural, serializer, example, delete_note):
  list_create = extend_schema_view(
    get=extend_schema(
      operation_id=f"inventory_{plural.lower()}_list",
      summary=f"List {plural}",
      description=f"Returns all {plural.lower()} of the logged-in user's business. Not paginated.",
      responses={
        200: resp(f"{label} list.",
                  ok_example(plural, f"{label} list fetched.", data=[example])),
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        429: THROTTLED_RESPONSE,
      },
    ),
    post=extend_schema(
      summary=f"Create {label}",
      description=(
        f"Creates a {label.lower()} in the logged-in user's business. The name must be "
        "unique within the business, ignoring upper and lower case. "
        "The business is set by the server. " + OWNER_NOTE
      ),
      request=serializer,
      examples=[
        OpenApiExample(f"Create {label}", value={"name": example["name"]}, request_only=True),
      ],
      responses={
        201: resp(f"{label} created.",
                  ok_example("Created", f"{label} created.", data=example)),
        400: validation_cases(
          ("Missing Name", {"name": ["This field is required."]}),
          ("Duplicate Name", {"name": [f"{label} with this name already exists."]}),
        ),
        401: UNAUTHORIZED_RESPONSE,
        403: OWNER_ONLY_RESPONSE,
        429: THROTTLED_RESPONSE,
      },
    ),
  )

  detail = extend_schema_view(
    get=extend_schema(
      summary=f"Get {label}",
      responses={
        200: resp(f"{label} details.",
                  ok_example(label, f"{label} fetched.", data=example)),
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: not_found(label),
        429: THROTTLED_RESPONSE,
      },
    ),
    put=extend_schema(
      summary=f"Replace {label}",
      description="Full update. `name` is required. " + OWNER_NOTE,
      request=serializer,
      responses={
        200: resp(f"{label} updated.",
                  ok_example("Updated", f"{label} updated.", data=example)),
        400: validation_cases(
          ("Missing Name", {"name": ["This field is required."]}),
          ("Duplicate Name", {"name": [f"{label} with this name already exists."]}),
        ),
        401: UNAUTHORIZED_RESPONSE,
        403: OWNER_ONLY_RESPONSE,
        404: not_found(label),
        429: THROTTLED_RESPONSE,
      },
    ),
    patch=extend_schema(
      summary=f"Update {label}",
      description="Partial update. Send only the fields you want to change. " + OWNER_NOTE,
      request=serializer,
      examples=[
        OpenApiExample(f"Rename {label}", value={"name": "New Name"}, request_only=True),
      ],
      responses={
        200: resp(f"{label} updated.",
                  ok_example("Updated", f"{label} updated.", data=example)),
        400: validation_cases(
          ("Blank Name", {"name": ["This field may not be blank."]}),
          ("Duplicate Name", {"name": [f"{label} with this name already exists."]}),
        ),
        401: UNAUTHORIZED_RESPONSE,
        403: OWNER_ONLY_RESPONSE,
        404: not_found(label),
        429: THROTTLED_RESPONSE,
      },
    ),
    delete=extend_schema(
      summary=f"Delete {label}",
      description=f"Permanently deletes the {label.lower()}. {delete_note} {OWNER_NOTE}",
      responses={
        200: resp(f"{label} deleted.", ok_example("Deleted", f"{label} deleted.")),
        401: UNAUTHORIZED_RESPONSE,
        403: OWNER_ONLY_RESPONSE,
        404: not_found(label),
        429: THROTTLED_RESPONSE,
      },
    ),
  )
  return list_create, detail


category_list_create_docs, category_detail_docs = name_only_crud_docs(
  "Category", "Categories", CategorySerializer, CATEGORY_EXAMPLE,
  "Products in this category are kept and become uncategorised.",
)

warehouse_docs = extend_schema_view(
  get=extend_schema(
    summary="Get Warehouse",
    description=(
      "Returns the business's warehouse. Every business has exactly one "
      "centralized warehouse, created automatically, and all products are stored "
      "in it. There is no create or delete: POST and DELETE return 405."
    ),
    responses={
      200: resp("Warehouse details.",
                ok_example("Warehouse", "Warehouse fetched.", data=WAREHOUSE_EXAMPLE)),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
  put=extend_schema(
    summary="Replace Warehouse Details",
    description="Full update of the warehouse details. `name` is required. " + OWNER_NOTE,
    request=WarehouseSerializer,
    examples=[
      OpenApiExample(
        "Replace Warehouse",
        value={"name": WAREHOUSE_EXAMPLE["name"], "address": WAREHOUSE_EXAMPLE["address"]},
        request_only=True,
      ),
    ],
    responses={
      200: resp("Warehouse updated.",
                ok_example("Updated", "Warehouse updated.", data=WAREHOUSE_EXAMPLE)),
      400: validation_cases(
        ("Missing Name", {"name": ["This field is required."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
  patch=extend_schema(
    summary="Update Warehouse Details",
    description="Partial update. Send only the fields you want to change. " + OWNER_NOTE,
    request=WarehouseSerializer,
    examples=[
      OpenApiExample("Rename Warehouse", value={"name": "Central Godown"}, request_only=True),
    ],
    responses={
      200: resp("Warehouse updated.",
                ok_example("Updated", "Warehouse updated.", data=WAREHOUSE_EXAMPLE)),
      400: validation_cases(
        ("Blank Name", {"name": ["This field may not be blank."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

OUTLET_ID = "4c8e2b71-6a39-4d05-b2f8-0e7a1d9c5b36"
DISPATCH_ID = "e5a1c7d3-8b24-4f60-9c1e-3a6d2b8f4e70"

OUTLET_EXAMPLE = {
  "id": OUTLET_ID,
  "name": "Andheri Store",
  "address": "Shop 4, Link Road, Andheri West, Mumbai",
  "is_active": True,
  "created_at": "2026-10-05T10:00:00Z",
  "updated_at": "2026-10-05T10:00:00Z",
}

DISPATCH_EXAMPLE = {
  "id": DISPATCH_ID,
  "number": "DN-0001",
  "outlet": OUTLET_ID,
  "outlet_name": "Andheri Store",
  "dispatch_date": "2026-10-10",
  "notes": "",
  "created_by_email": "staff@example.com",
  "items": [
    {
      "id": 1,
      "product": PRODUCT_ID,
      "product_name": "Parle-G Biscuits 200g",
      "product_sku": "PARLEG-200",
      "quantity": 12,
    }
  ],
  "created_at": "2026-10-10T09:30:00Z",
}

OUTLET_NOTE = (
  "An outlet is only a dispatch destination: its stock is not tracked. "
  "Employees can create outlets (so they can add one while dispatching); "
  "only the owner can edit or delete them."
)

outlet_list_create_docs = extend_schema_view(
  get=extend_schema(
    operation_id="inventory_outlets_list",
    summary="List Outlets",
    description=(
      "Returns all outlets of the logged-in user's business. Not paginated. "
      "Use `is_active=true` to get only outlets that can receive dispatches."
    ),
    parameters=[
      OpenApiParameter(
        "is_active", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description="`true` or `false`. Any other value is ignored.",
      ),
    ],
    responses={
      200: resp("Outlet list.",
                ok_example("Outlets", "Outlet list fetched.", data=[OUTLET_EXAMPLE])),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
  post=extend_schema(
    summary="Create Outlet",
    description=(
      "Creates an outlet in the logged-in user's business. The name must be unique "
      "within the business, ignoring upper and lower case. " + OUTLET_NOTE
    ),
    request=OutletSerializer,
    examples=[
      OpenApiExample(
        "Create Outlet",
        value={"name": "Andheri Store", "address": "Shop 4, Link Road, Andheri West, Mumbai"},
        request_only=True,
      ),
    ],
    responses={
      201: resp("Outlet created.",
                ok_example("Created", "Outlet created.", data=OUTLET_EXAMPLE)),
      400: validation_cases(
        ("Missing Name", {"name": ["This field is required."]}),
        ("Duplicate Name", {"name": ["Outlet with this name already exists."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

outlet_detail_docs = extend_schema_view(
  get=extend_schema(
    summary="Get Outlet",
    responses={
      200: resp("Outlet details.",
                ok_example("Outlet", "Outlet fetched.", data=OUTLET_EXAMPLE)),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: not_found("Outlet"),
      429: THROTTLED_RESPONSE,
    },
  ),
  put=extend_schema(
    summary="Replace Outlet",
    description="Full update. `name` is required. " + OWNER_NOTE,
    request=OutletSerializer,
    responses={
      200: resp("Outlet updated.",
                ok_example("Updated", "Outlet updated.", data=OUTLET_EXAMPLE)),
      400: validation_cases(
        ("Missing Name", {"name": ["This field is required."]}),
        ("Duplicate Name", {"name": ["Outlet with this name already exists."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: not_found("Outlet"),
      429: THROTTLED_RESPONSE,
    },
  ),
  patch=extend_schema(
    summary="Update Outlet",
    description=(
      "Partial update. Send only the fields you want to change. Set `is_active` to "
      "false to stop an outlet receiving dispatches while keeping its history. "
      + OWNER_NOTE
    ),
    request=OutletSerializer,
    examples=[
      OpenApiExample("Deactivate Outlet", value={"is_active": False}, request_only=True),
    ],
    responses={
      200: resp("Outlet updated.",
                ok_example("Updated", "Outlet updated.", data=OUTLET_EXAMPLE)),
      400: validation_cases(
        ("Blank Name", {"name": ["This field may not be blank."]}),
        ("Duplicate Name", {"name": ["Outlet with this name already exists."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: not_found("Outlet"),
      429: THROTTLED_RESPONSE,
    },
  ),
  delete=extend_schema(
    summary="Delete Outlet",
    description=(
      "Permanently deletes an outlet that has never received a dispatch. If it has "
      "dispatch history, a 400 is returned: set `is_active` to false instead. "
      + OWNER_NOTE
    ),
    responses={
      200: resp("Outlet deleted.", ok_example("Deleted", "Outlet deleted.")),
      400: validation_cases(
        ("Has Dispatch History",
         ["This outlet has dispatch history. Set is_active to false instead."]),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: not_found("Outlet"),
      429: THROTTLED_RESPONSE,
    },
  ),
)

DISPATCH_LIST_PARAMS = [
  OpenApiParameter("outlet", OpenApiTypes.UUID, OpenApiParameter.QUERY,
                   description="Only dispatches to this outlet id."),
  OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY,
                   description="Dispatch date on or after this date (YYYY-MM-DD)."),
  OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY,
                   description="Dispatch date on or before this date (YYYY-MM-DD)."),
  OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY,
                   description="Page number, starting at 1."),
  OpenApiParameter("page_size", OpenApiTypes.INT, OpenApiParameter.QUERY,
                   description="Dispatches per page."),
]

dispatch_list_create_docs = extend_schema_view(
  get=extend_schema(
    operation_id="inventory_dispatches_list",
    summary="List Dispatches",
    description=(
      "Returns a page of dispatch notes of the logged-in user's business, newest "
      "first, with their items. Results are paginated."
    ),
    parameters=DISPATCH_LIST_PARAMS,
    responses={
      200: resp("One page of dispatches.",
                ok_example("Dispatch page", "Dispatch list fetched.", data={
                  "count": 1, "next": None, "previous": None,
                  "results": [DISPATCH_EXAMPLE],
                })),
      400: validation_cases(
        ("Invalid Outlet", {"outlet": ["Invalid outlet UUID."]}),
        ("Invalid Date", {"from": ["Use YYYY-MM-DD."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
  post=extend_schema(
    summary="Record Dispatch",
    description=(
      "Sends stock from the warehouse to an outlet. Creates one dispatch note "
      "(number like `DN-0001`, set by the server) and removes each item's quantity "
      "from stock through the ledger. It is all or nothing: if any item has "
      "insufficient stock, nothing is saved. Repeated products are merged. "
      "`dispatch_date` is optional (defaults to today, cannot be in the future). "
      "The outlet must be active. Owner and employees can record dispatches. "
      "Dispatches cannot be edited or deleted: correct a mistake with the "
      "adjust-stock endpoint. Accepts JSON."
    ),
    request=DispatchCreateSerializer,
    examples=[
      OpenApiExample(
        "Dispatch To Outlet",
        value={
          "outlet": OUTLET_ID,
          "dispatch_date": "2026-10-10",
          "notes": "Weekly refill",
          "items": [{"product": PRODUCT_ID, "quantity": 12}],
        },
        request_only=True,
      ),
    ],
    responses={
      201: resp("Dispatch recorded.",
                ok_example("Created", "Dispatch recorded.", data=DISPATCH_EXAMPLE)),
      400: validation_cases(
        ("Missing Fields", {
          "outlet": ["This field is required."],
          "items": ["This field is required."],
        }),
        ("Empty Items", {"items": ["This list may not be empty."]}),
        ("Future Date", {"dispatch_date": ["Dispatch date cannot be in the future."]}),
        ("Insufficient Stock",
         {"change": ["Insufficient stock for Parle-G Biscuits 200g."]}),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

dispatch_detail_docs = extend_schema_view(
  get=extend_schema(
    summary="Get Dispatch",
    responses={
      200: resp("Dispatch details.",
                ok_example("Dispatch", "Dispatch fetched.", data=DISPATCH_EXAMPLE)),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: not_found("Dispatch"),
      429: THROTTLED_RESPONSE,
    },
  ),
)
