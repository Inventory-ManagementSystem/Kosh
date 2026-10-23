from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

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
    PO_DETAIL_NOT_FOUND_RESPONSE,
    SUPPLIER_PO_NOTE,

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

PO_PDF_CONTENT = (
  "The purchase order as a PDF: buyer details with the owner's name and email, "
  "supplier details with GSTIN, order number and date, the RFQ it came from, "
  "delivery date (marked if the supplier set a later expected date at dispatch), "
  "payment terms (the advance, whether it is paid or still due, and the balance "
  "after delivery), every line with quantity, unit price, GST and totals, and the "
  "order totals. It shows the quantities that were ordered; the invoice shows what "
  "was dispatched. The PDF is built from the current data on every request. File "
  "name `<PO number>-<other party>.pdf`. Use the order `id` from List Orders. "
)

po_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_orders_pdf",
    summary="Download Order PDF",
    description=(
      PO_PDF_CONTENT + "The owner can download an order in any status, including "
      "`awaiting_advance` and `cancelled`. " + ACCESS_NOTE + " " + PDF_NOTE
    ),
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: PO_DETAIL_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_po_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_supplier_orders_pdf",
    summary="Supplier: Download Order PDF",
    description=PO_PDF_CONTENT + SUPPLIER_PO_NOTE + " " + PDF_NOTE,
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: PO_DETAIL_NOT_FOUND_RESPONSE,
    },
  ),
)

GRN_PDF_NOT_FOUND_RESPONSE = resp(
  "No such goods receipt for this user. A receipt that belongs to someone else "
  "also returns this.",
  err_example("Not Found", "No GoodsReceipt matches the given query.", "NOT_FOUND"),
)

GRN_PDF_CONTENT = (
  "The goods receipt note as a PDF: buyer and supplier details, receipt number and "
  "date, the purchase order and invoice it belongs to, and every line with the "
  "ordered, dispatched, received, rejected and accepted quantities and the credit "
  "for that line (the three-way match). A discrepancies table lists each shortage, "
  "rejection or excess, or states that there are none. It ends with the invoice "
  "settlement: invoice total, goods receipt credit, advance applied and the balance "
  "payable, plus the part of the advance the supplier owes back if there is one. "
  "The PDF is built from the current data on every request. File name "
  "`<GRN number>-<other party>.pdf`. Use the receipt `id` from List Goods Receipts. "
)

grn_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_goods_receipts_pdf",
    summary="Download Goods Receipt PDF",
    description=(
      GRN_PDF_CONTENT
      + "It also shows the name of the staff member who confirmed the delivery. "
      + ACCESS_NOTE + " " + PDF_NOTE
    ),
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: GRN_PDF_NOT_FOUND_RESPONSE,
    },
  ),
)

supplier_grn_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_supplier_goods_receipts_pdf",
    summary="Supplier: Download Goods Receipt PDF",
    description=(
      GRN_PDF_CONTENT
      + "Unlike the buyer's copy, it does not show the name of the buyer's staff. "
      "Supplier only; a supplier can download receipts only for their own orders, "
      "and a receipt for someone else's order returns a 404. " + PDF_NOTE
    ),
    responses={
      **PDF_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      404: GRN_PDF_NOT_FOUND_RESPONSE,
    },
  ),
)

def _weight_parameter(name, label):
  return OpenApiParameter(
    f"weight_{name}", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=False,
    description=(
      f"How much {label} matters, from 0 to 1000. Weights are relative, so they "
      "don't need to add up to 100. Send the slider values for all four weights, or "
      "none. If none are sent, the defaults are used (price 50, delivery 25, payment "
      "10, reliability 15). If any is sent, the ones left out count as 0."
    ),
  )

COMPARISON_PARAMETERS = [
  _weight_parameter("price", "the total price"),
  _weight_parameter("delivery", "fast delivery"),
  _weight_parameter("payment", "payment terms (a smaller advance scores higher)"),
  _weight_parameter("reliability", "supplier reliability"),
  OpenApiParameter(
    "sort", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=["price"],
    description=(
      "Send `price` to list the quotations from the lowest total price instead of "
      "from the best score. The rank and score columns still show the score-based "
      "result. Any other value is ignored."
    ),
  ),
]

rfq_comparison_pdf_docs = extend_schema_view(
  get=extend_schema(
    tags=TAGS,
    operation_id="procurement_rfqs_quotations_pdf",
    summary="Download Quotation Comparison PDF",
    description=(
      "The ranked comparison of an RFQ's quotations as a PDF, for the owner to keep "
      "or share when deciding: RFQ details, the recommended supplier, a ranking table "
      "(supplier, badges `recommended` / `cheapest` / `fastest`, total, advance, "
      "delivery time, score), the score breakdown per criterion with the weights "
      "used, and a short note on how the score is calculated. Withdrawn quotations "
      "are left out. An RFQ with no quotations still returns a PDF that says so.\n\n"
      "It uses the same ranking and the same query parameters as List Quotations for "
      "RFQ, so pass the same weights and `sort` the screen is currently showing and "
      "the PDF will match it. The weights are not remembered between requests; "
      "without them the default weights are used. A criterion that no quotation can "
      "be scored on yet (reliability, while no data exists) is ignored and the PDF "
      "says so. Owner and employees only; there is no supplier version, because the "
      "comparison shows every supplier's prices. File name `<RFQ number>-comparison.pdf`. "
      + ACCESS_NOTE + " " + PDF_NOTE
    ),
    parameters=COMPARISON_PARAMETERS,
    responses={
      **PDF_RESPONSE,
      400: resp(
        "The weights are not valid.",
        err_example(
          "Bad Weight", "weight_price must be a number from 0 to 1000.", "INVALID_WEIGHTS",
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
