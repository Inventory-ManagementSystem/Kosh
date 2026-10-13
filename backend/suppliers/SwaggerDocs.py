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

from .serializers import OwnerSupplierSerializer


INVITED_SUPPLIER_EXAMPLE = {
  "id": "6b2e9d14-3f7a-4c80-b5d1-9a0e8c7f2d34",
  "email": "orders@sharmatraders.in",
  "phone": "9876543210",
  "label": "Biscuit vendor",
  "is_active": True,
  "display_name": "Biscuit vendor",
  "status": "invited",
  "company_name": None,
  "city": None,
  "pincode": None,
  "category_names": [],
  "account_verified": False,
  "created_at": "2026-10-12T10:00:00Z",
  "updated_at": "2026-10-12T10:00:00Z",
}

LINKED_SUPPLIER_EXAMPLE = {
  "id": "a41f7c90-2d5b-4e68-8c13-5b9e0d7a6f21",
  "email": "sales@guptawholesale.in",
  "phone": "9123456780",
  "label": "",
  "is_active": True,
  "display_name": "Gupta Wholesale",
  "status": "linked",
  "company_name": "Gupta Wholesale",
  "city": "Delhi",
  "pincode": "110006",
  "category_names": ["Beverages", "Groceries and FMCG"],
  "account_verified": True,
  "created_at": "2026-10-12T10:05:00Z",
  "updated_at": "2026-10-12T10:05:00Z",
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
  "No such supplier in this business.",
  err_example("Not Found", "No Supplier matches the given query.", "NOT_FOUND"),
)

EMAIL_TAKEN_RESPONSE = resp(
  "The same email was added to this business at the same moment.",
  err_example(
    "Email Taken", "This supplier is already in your list.", "SUPPLIER_EXISTS"
  ),
)


def validation_cases(*cases):
  return resp(
    "Validation error.",
    *[
      err_example(name, "Validation failed.", "VALIDATION_ERROR", errors=errors)
      for name, errors in cases
    ],
  )


RECORD_NOTE = (
  "A supplier record is only a link between your business and a supplier's own "
  "account. You enter just the email (and optionally a phone and a label); the "
  "company name, city, pincode and categories come from the supplier's own "
  "registration and are read-only here, so sending them is ignored."
)

FIELD_NOTE = (
  "`email` is required: it is trimmed, stored in lower case, and must be unique "
  "within the business, ignoring upper and lower case. `phone` (up to 16 "
  "characters) is optional. `label` (up to 100 characters) is an optional nickname "
  "shown until the supplier has an account. `is_active` defaults to true; an "
  "inactive supplier is kept but is not sent new RFQs."
)

STATUS_NOTE = (
  "`status` is `linked` when a supplier account with this email exists, and "
  "`invited` when it does not. For a linked record, `company_name`, `city`, "
  "`pincode`, `category_names` and `account_verified` come from the supplier's "
  "account; for an invited one they are null, empty or false. `display_name` is "
  "the company name when linked, otherwise the label, otherwise the email. An "
  "invited supplier cannot send quotations until they register with that email."
)

LINK_NOTE = (
  "Linking is automatic: at the moment you add the email if the account already "
  "exists, or later when the supplier registers with that email."
)

OWNER_NOTE = "Owner only; employees get a 403."

COMMON_FIELD_ERRORS = (
  ("Invalid Email", {"email": ["Enter a valid email address."]}),
  ("Duplicate Email", {"email": ["This supplier is already in your list."]}),
  ("Invalid Phone", {"phone": ["Enter a valid phone number."]}),
  ("Phone Too Long", {"phone": ["Ensure this field has no more than 16 characters."]}),
  ("Label Too Long", {"label": ["Ensure this field has no more than 100 characters."]}),
  ("Invalid Is Active", {"is_active": ["Must be a valid boolean."]}),
)

CREATE_ERRORS = (
  ("Missing Email", {"email": ["This field is required."]}),
  ("Blank Email", {"email": ["This field may not be blank."]}),
  *COMMON_FIELD_ERRORS,
)

UPDATE_ERRORS = (
  ("Blank Email", {"email": ["This field may not be blank."]}),
  *COMMON_FIELD_ERRORS,
)


owner_supplier_list_create_docs = extend_schema_view(
  get=extend_schema(
    operation_id="suppliers_my_suppliers_list",
    summary="List My Suppliers",
    description=(
      "Returns the suppliers of the logged-in user's business, newest first. This "
      "is the business's own supplier list, the recipient list for RFQs. Not "
      "paginated. Both the owner and employees can read it. "
      + RECORD_NOTE + " " + STATUS_NOTE
    ),
    parameters=[
      OpenApiParameter(
        "search", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description=(
          "Matches part of the email, the label or the linked company name, "
          "ignoring upper and lower case."
        ),
      ),
      OpenApiParameter(
        "is_active", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description="`true` or `false`. Any other value is ignored and all suppliers are returned.",
      ),
    ],
    responses={
      200: resp(
        "Supplier list.",
        ok_example(
          "Suppliers", "Supplier list fetched.",
          data=[LINKED_SUPPLIER_EXAMPLE, INVITED_SUPPLIER_EXAMPLE],
        ),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
    },
  ),
  post=extend_schema(
    summary="Add Supplier",
    description=(
      "Adds a supplier to the logged-in user's business. The business is set by "
      "the server, never by the request body. " + RECORD_NOTE + " " + FIELD_NOTE
      + " " + LINK_NOTE + " If no account exists yet, an invitation email is sent "
      "to the supplier asking them to sign up and register their agency; if that "
      "email fails to send, the supplier is still added. " + STATUS_NOTE + " "
      + OWNER_NOTE + " Accepts JSON."
    ),
    request=OwnerSupplierSerializer,
    examples=[
      OpenApiExample(
        "Email Only",
        value={"email": "orders@sharmatraders.in"},
        request_only=True,
      ),
      OpenApiExample(
        "With Phone And Label",
        value={
          "email": "orders@sharmatraders.in",
          "phone": "9876543210",
          "label": "Biscuit vendor",
        },
        request_only=True,
      ),
    ],
    responses={
      201: resp(
        "Supplier added.",
        ok_example("Invited", "Supplier created.", data=INVITED_SUPPLIER_EXAMPLE),
        ok_example("Already Registered", "Supplier created.", data=LINKED_SUPPLIER_EXAMPLE),
      ),
      400: validation_cases(*CREATE_ERRORS),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      409: EMAIL_TAKEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
)

owner_supplier_detail_docs = extend_schema_view(
  get=extend_schema(
    summary="Get My Supplier",
    description=(
      "Returns one supplier of the business. Both the owner and employees can read "
      "it. " + STATUS_NOTE
    ),
    responses={
      200: resp(
        "Supplier details.",
        ok_example("Linked", "Supplier fetched.", data=LINKED_SUPPLIER_EXAMPLE),
        ok_example("Invited", "Supplier fetched.", data=INVITED_SUPPLIER_EXAMPLE),
      ),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
    },
  ),
  patch=extend_schema(
    summary="Update My Supplier",
    description=(
      "Partial update. Send only the fields you want to change; there is no PUT. "
      "You can change `email`, `phone`, `label` and `is_active`. Changing `email` "
      "re-checks for a supplier account with the new email: the record is linked to "
      "it if one exists, and becomes unlinked (`invited`) if there is none. No "
      "invitation email is sent when the email changes. Set `is_active` to false to "
      "stop sending RFQs to a supplier while keeping its history. " + RECORD_NOTE
      + " " + OWNER_NOTE + " Accepts JSON."
    ),
    request=OwnerSupplierSerializer,
    examples=[
      OpenApiExample("Change Phone", value={"phone": "9123456780"}, request_only=True),
      OpenApiExample("Change Label", value={"label": "Main biscuit vendor"}, request_only=True),
      OpenApiExample(
        "Change Email (re-links)",
        value={"email": "sales@sharmatraders.in"},
        request_only=True,
      ),
      OpenApiExample("Deactivate Supplier", value={"is_active": False}, request_only=True),
    ],
    responses={
      200: resp(
        "Supplier updated.",
        ok_example("Updated", "Supplier updated.", data=LINKED_SUPPLIER_EXAMPLE),
      ),
      400: validation_cases(*UPDATE_ERRORS),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: NOT_FOUND_RESPONSE,
      409: EMAIL_TAKEN_RESPONSE,
      429: THROTTLED_RESPONSE,
    },
  ),
  delete=extend_schema(
    summary="Delete My Supplier",
    description=(
      "Permanently deletes a supplier that has never been sent an RFQ. If it has "
      "RFQ history, nothing is deleted and a 409 is returned: set `is_active` to "
      "false instead. Deleting a record never affects the supplier's own account. "
      + OWNER_NOTE
    ),
    responses={
      200: resp("Supplier deleted.", ok_example("Deleted", "Supplier deleted.")),
      401: UNAUTHORIZED_RESPONSE,
      403: OWNER_ONLY_RESPONSE,
      404: NOT_FOUND_RESPONSE,
      409: resp(
        "The supplier has RFQ history.",
        err_example(
          "Has History",
          "This supplier has RFQ history. Set is_active to false instead.",
          "SUPPLIER_HAS_HISTORY",
        ),
      ),
      429: THROTTLED_RESPONSE,
    },
  ),
)
