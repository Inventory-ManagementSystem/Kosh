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
  CategorySerializer,
  ProductSerializer,
  StockAdjustmentSerializer,
  WarehouseSerializer,
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
  "created_at": "2026-10-05T10:00:00Z",
  "updated_at": "2026-10-05T10:00:00Z",
}


FORBIDDEN_RESPONSE = resp(
  "User has no registered business.",
  err_example(
    "No Business",
    "You do not have permission to perform this action.",
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
  "`image` file. `category` and `warehouse` must be ids from this business; send "
  "the field empty to clear it."
)

QUANTITY_NOTE = (
  "`quantity` can only be set when the product is created. On update it is rejected "
  "with a 400, because stock changes must go through the adjust-stock endpoint."
)


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
    "warehouse", OpenApiTypes.UUID, OpenApiParameter.QUERY,
    description="Only products stored in this warehouse id.",
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
  "quantity": 120,
  "low_stock_threshold": 10,
  "category": CATEGORY_ID,
  "warehouse": WAREHOUSE_ID,
}

PRODUCT_UPDATE_EXAMPLE = {k: v for k, v in PRODUCT_WRITE_EXAMPLE.items() if k != "quantity"}

product_list_create_docs = extend_schema_view(
  get=extend_schema(
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
      "case and must be unique within the business. `quantity` sets the opening stock. "
      + PRODUCT_BODY_NOTE
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
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
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
      + QUANTITY_NOTE + " " + PRODUCT_BODY_NOTE
    ),
    request=ProductSerializer,
    examples=[
      OpenApiExample("Replace Product", value=PRODUCT_UPDATE_EXAMPLE, request_only=True),
    ],
    responses={
      200: resp("Product updated.",
                ok_example("Updated", "Product updated.", data=PRODUCT_EXAMPLE)),
      400: validation_cases(
        ("Missing Fields", {"sku": ["This field is required."]}),
        ("Duplicate SKU", {"sku": ["SKU already exists in your inventory."]}),
        ("Quantity Not Allowed", {
          "quantity": ["Use the adjust-stock endpoint to change stock."],
        }),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
  patch=extend_schema(
    summary="Update Product",
    description=(
      "Partial update. Send only the fields you want to change. "
      + QUANTITY_NOTE + " " + PRODUCT_BODY_NOTE
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
        ("Quantity Not Allowed", {
          "quantity": ["Use the adjust-stock endpoint to change stock."],
        }),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
  delete=extend_schema(
    summary="Delete Product",
    description="Permanently deletes the product. To keep it but hide it, set `is_active` to false instead.",
    responses={
      200: resp("Product deleted.", ok_example("Deleted", "Product deleted.")),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: not_found("Product"),
      429: THROTTLED_RESPONSE,
    },
  ),
)

product_adjust_stock_docs = extend_schema_view(
  post=extend_schema(
    summary="Adjust Product Stock",
    description=(
      "Adds to or removes from a product's stock. `change` is a whole number between "
      "-1,000,000 and 1,000,000 and cannot be zero: positive adds stock, negative "
      "removes it. The product row is locked while the change is applied, so "
      "simultaneous adjustments can't clash. If the result would be below zero, nothing "
      "changes and a 400 is returned. `reason` is an optional note (up to 255 "
      "characters); it is accepted but currently not saved. Accepts JSON."
    ),
    request=StockAdjustmentSerializer,
    examples=[
      OpenApiExample("Add Stock", value={"change": 50, "reason": "New delivery"}, request_only=True),
      OpenApiExample("Remove Stock", value={"change": -5}, request_only=True),
    ],
    responses={
      200: resp("Stock updated. Returns the full product.",
                ok_example("Stock Updated", "Stock updated.",
                           data={**PRODUCT_EXAMPLE, "quantity": 170})),
      400: validation_cases(
        ("Insufficient Stock", {"change": ["Insufficient stock."]}),
        ("Zero Change", {"change": ["Change cannot be zero."]}),
        ("Invalid Change", {"change": ["A valid integer is required."]}),
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
        "The business is set by the server."
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
        403: FORBIDDEN_RESPONSE,
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
      description="Full update. `name` is required.",
      request=serializer,
      responses={
        200: resp(f"{label} updated.",
                  ok_example("Updated", f"{label} updated.", data=example)),
        400: validation_cases(
          ("Missing Name", {"name": ["This field is required."]}),
          ("Duplicate Name", {"name": [f"{label} with this name already exists."]}),
        ),
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: not_found(label),
        429: THROTTLED_RESPONSE,
      },
    ),
    patch=extend_schema(
      summary=f"Update {label}",
      description="Partial update. Send only the fields you want to change.",
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
        403: FORBIDDEN_RESPONSE,
        404: not_found(label),
        429: THROTTLED_RESPONSE,
      },
    ),
    delete=extend_schema(
      summary=f"Delete {label}",
      description=f"Permanently deletes the {label.lower()}. {delete_note}",
      responses={
        200: resp(f"{label} deleted.", ok_example("Deleted", f"{label} deleted.")),
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
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

warehouse_list_create_docs, warehouse_detail_docs = name_only_crud_docs(
  "Warehouse", "Warehouses", WarehouseSerializer, WAREHOUSE_EXAMPLE,
  "Products stored here are kept and are left without a warehouse.",
)
