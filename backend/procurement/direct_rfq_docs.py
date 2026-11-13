from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from accounts.swagger import UNAUTHORIZED_RESPONSE, err_example, ok_example, resp

from .SwaggerDocs import (
  OWNER_NOTE,
  OWNER_ONLY_RESPONSE,
  RFQ_DETAIL_EXAMPLE,
  TAGS_RFQ,
  THROTTLED_RESPONSE,
)
from .serializers import DirectRFQCreateSerializer

DIRECT_RFQ_EXAMPLE = {
  **RFQ_DETAIL_EXAMPLE,
  "include_platform_pool": True,
  "auto_generated": False,
  "recipient_count": 1,
  "quoted_count": 0,
}

direct_rfq_create_docs = extend_schema_view(
  post=extend_schema(
    tags=TAGS_RFQ,
    operation_id="procurement_rfqs_direct_create",
    summary="Send RFQ To One Supplier",
    description=(
      "Sends an RFQ to one supplier the owner picked, for example from the supplier "
      "map. `supplier` is the supplier's profile `id` from `GET /suppliers/nearby/`; "
      "it must be verified. `items` holds 1 to 50 products of this business, each "
      "once, with a quantity. Every product needs a supply category that the "
      "supplier sells. Products are grouped by supply category and one RFQ is "
      "created per category, all sent only to this supplier, so the response is a "
      "list. The supplier is recorded as your own supplier if they are in your "
      "supplier list, otherwise as a platform supplier (`include_platform_pool` is "
      "then true). An open low-stock alert for any of the products is linked to "
      "the new RFQ and becomes `rfq_created`. The deadline is 3 days from now. "
      "All or nothing: if any product cannot be used, no RFQ is created. "
      + OWNER_NOTE + " Accepts JSON."
    ),
    request=DirectRFQCreateSerializer,
    examples=[
      OpenApiExample(
        "One Product",
        value={
          "supplier": "3f0c2a1e-8b7d-4c5e-9a10-2b3c4d5e6f70",
          "items": [{"product": "5d0c7e91-4b3a-4a28-8f16-c2e9a7b1d054", "quantity": 70}],
        },
        request_only=True,
      ),
      OpenApiExample(
        "Several Products With Notes",
        value={
          "supplier": "3f0c2a1e-8b7d-4c5e-9a10-2b3c4d5e6f70",
          "items": [
            {"product": "5d0c7e91-4b3a-4a28-8f16-c2e9a7b1d054", "quantity": 70},
            {"product": "8b2e4f17-6c3a-4d90-a1e5-7f0b9c2d3e48", "quantity": 40},
          ],
          "notes": "Deliver to the back gate.",
        },
        request_only=True,
      ),
    ],
    responses={
      201: resp(
        "RFQ sent.",
        ok_example("Sent", "RFQ sent.", data=[DIRECT_RFQ_EXAMPLE]),
      ),
      400: resp(
        "Validation error, or a product can't be sent to this supplier.",
        err_example("Unknown Supplier", "Validation failed.", "VALIDATION_ERROR",
          errors={"supplier": ['Invalid pk "3f0c2a1e-8b7d-4c5e-9a10-2b3c4d5e6f70" - object does not exist.']}),
        err_example("No Items", "Validation failed.", "VALIDATION_ERROR",
          errors={"items": ["This list may not be empty."]}),
        err_example("Duplicate Product", "Validation failed.", "VALIDATION_ERROR",
          errors={"items": ["Each product can be added only once."]}),
        err_example("Product Not Found", "Validation failed.", "VALIDATION_ERROR",
          errors={"items": ["One or more products were not found."]}),
        err_example("Invalid Quantity", "Validation failed.", "VALIDATION_ERROR",
          errors={"items": [{"quantity": ["Ensure this value is greater than or equal to 1."]}]}),
        err_example(
          "No Supply Category",
          "Set a supply category on Amul Milk 1L so we know which suppliers to ask.",
          "NO_SUPPLY_CATEGORY",
        ),
        err_example(
          "Category Not Supplied",
          "Sharma Traders doesn't supply Dairy.",
          "CATEGORY_NOT_SUPPLIED",
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)
