from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view

from accounts.swagger import (
  UNAUTHORIZED_RESPONSE,
  err_example,
  resp,
)

TAGS = ["PDF Documents"]

from .SwaggerDocs import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    NOT_SUPPLIER_RESPONSE,
    INVITATION_NOT_FOUND_RESPONSE,
    SUPPLIER_NOTE,
    ACCESS_NOTE,
    INVOICE_NOT_FOUND_RESPONSE,

)

PDF_RESPONSE = {(200, "application/pdf"): OpenApiTypes.BINARY}

PDF_NOTE = (
  "Returns the file itself (`Content-Type: application/pdf`, "
  "`Content-Disposition: attachment`), not JSON. Because the request needs the "
  "`Authorization` header, the frontend should fetch it and save the blob rather "
  "than use a plain link. Errors are still JSON. Amounts are shown as `Rs.` with "
  "Indian digit grouping and times in IST."
)

rfq_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_rfqs_pdf",
    summary="Download RFQ PDF",
    description=(
      "The RFQ as a PDF: buyer, RFQ number, quote-by deadline, issue date, expected "
      "delivery, items and notes. File name `<RFQ number>.pdf`. " + ACCESS_NOTE
      + " " + PDF_NOTE
    ),
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
    },
  ),
)

quotation_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_quotations_pdf",
    summary="Download Quotation PDF",
    description=(
      "A supplier's quotation as a PDF: supplier details with GSTIN, buyer, revision, "
      "status, validity, delivery date (marked if late), payment terms, each item with "
      "unit price, GST and totals, advance and balance, and remarks. Withdrawn quotations return "
      "404. File name `<RFQ number>-quotation-<supplier>.pdf`. Use the quotation `id` "
      "from List Quotations for RFQ. " + ACCESS_NOTE + " " + PDF_NOTE
    ),
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: resp(
        "No such quotation in this business, or it was withdrawn.",
        err_example("Not Found", "Quotation not found.", "NOT_FOUND"),
      ),
    },
  ),
)

supplier_rfq_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,            
    operation_id="procurement_supplier_rfqs_pdf",
    summary="Supplier: Download RFQ PDF",
    description="The same RFQ PDF the owner gets. " + SUPPLIER_NOTE + " " + PDF_NOTE,
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVITATION_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_quotation_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_supplier_quotation_pdf",
    summary="Supplier: Download My Quotation PDF",
    description=(
      "The supplier's own quotation on this RFQ as a PDF, including a withdrawn one. "
      + SUPPLIER_NOTE + " " + PDF_NOTE
    ),
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: resp(
        "No such invitation, or the supplier has not quoted yet.",
        err_example("Not Found", "RFQ not found.", "NOT_FOUND"),
        err_example("No Quotation", "You have not quoted on this RFQ yet.", "NO_QUOTATION"),
      ),
    },
  ),
)

INVOICE_PDF_CONTENT = (
  "The invoice as a PDF: supplier (issuer) details with GSTIN, buyer details with "
  "the owner's name and email, invoice number and date, purchase order number, "
  "dispatch date, tracking note and expected delivery (marked if late), every line "
  "with quantity, unit price, GST and totals, then subtotal, GST, invoice total, the "
  "advance paid and the balance payable. After the buyer confirms delivery with a "
  "goods receipt, the PDF also shows the goods receipt credit, and the amount of the "
  "advance the supplier owes back if there is one. The PDF is built from the current "
  "data on every request, so it always matches the invoice screen. File name "
  "`<invoice number>-<supplier>.pdf`. Use the invoice `id` from List Invoices. "
)

invoice_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_invoices_pdf",
    summary="Download Invoice PDF",
    description=INVOICE_PDF_CONTENT + ACCESS_NOTE + " " + PDF_NOTE,
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: INVOICE_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_invoice_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_supplier_invoices_pdf",
    summary="Supplier: Download Invoice PDF",
    description=(
      INVOICE_PDF_CONTENT
      + "Supplier only; an invoice of another supplier returns a 404. " + PDF_NOTE
    ),
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: INVOICE_NOT_FOUND_RESPONSE,
    },
  ),
)
