from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from accounts.permissions import HasBusinessAccess
from accounts.responses import error_response
from suppliers.permissions import IsSupplier

from . import pdf
from .models import RFQ, GoodsReceipt,  Invoice, Quotation, RFQRecipient, PurchaseOrder
from .PdfDocs import (
  quotation_pdf_docs,
  rfq_pdf_docs,
  supplier_quotation_pdf_docs,
  supplier_rfq_pdf_docs,
  invoice_pdf_docs,
  supplier_invoice_pdf_docs,
  po_pdf_docs,
  supplier_po_pdf_docs,
  grn_pdf_docs,
  supplier_grn_pdf_docs,
  rfq_comparison_pdf_docs,

)
from .renderers import PDFRenderer
from .views import get_invitation, invoice_queryset, po_queryset, supplier_po_base, grn_queryset, supplier_grn_base
from .ranking import WeightError, parse_weights, rank_quotations


def pdf_response(content, filename):
  response = HttpResponse(content, content_type="application/pdf")
  response["Content-Disposition"] = f'attachment; filename="{filename}"'
  return response


def quotation_filename(quotation):
  company = slugify(quotation.supplier_profile.company_name) or "supplier"
  return f"{quotation.rfq.number}-quotation-{company}.pdf"


def quotation_for_pdf(**filters):
  return (
    Quotation.objects.filter(**filters)
    .select_related("rfq__business", "supplier_profile__user")
    .prefetch_related("items__rfq_item", "rfq__items__product")
    .first()
  )


class PDFView(APIView):
  renderer_classes = [JSONRenderer, PDFRenderer]


@rfq_pdf_docs
class RFQPdfApi(PDFView):
  permission_classes = [HasBusinessAccess]
  def get(self, request, pk):
    rfq = get_object_or_404(
      RFQ.objects.select_related("business").prefetch_related("items__product__category"),
      pk=pk, business=request.business,
    )
    return pdf_response(pdf.rfq_pdf(rfq), f"{rfq.number}.pdf")


@quotation_pdf_docs
class QuotationPdfApi(PDFView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    quotation = quotation_for_pdf(pk=pk, rfq__business=request.business)
    if quotation is None or quotation.status == Quotation.Status.WITHDRAWN:
      raise NotFound("Quotation not found.")
    return pdf_response(pdf.quotation_pdf(quotation), quotation_filename(quotation))


@supplier_rfq_pdf_docs
class SupplierRFQPdfApi(PDFView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    recipient = get_invitation(
      RFQRecipient.objects.filter(supplier_profile=request.supplier)
      .select_related("rfq__business")
      .prefetch_related("rfq__items__product__category"),
      pk,
    )
    return pdf_response(pdf.rfq_pdf(recipient.rfq), f"{recipient.rfq.number}.pdf")


@supplier_quotation_pdf_docs
class SupplierQuotationPdfApi(PDFView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    recipient = get_invitation(
      RFQRecipient.objects.filter(supplier_profile=request.supplier), pk
    )
    quotation = quotation_for_pdf(recipient=recipient)
    if quotation is None:
      return error_response(
        "You have not quoted on this RFQ yet.", "NO_QUOTATION",
        status=status.HTTP_404_NOT_FOUND,
      )
    return pdf_response(pdf.quotation_pdf(quotation), quotation_filename(quotation))

def invoice_filename(invoice):
  company = slugify(invoice.supplier_profile.company_name) or "supplier"
  return f"{invoice.number}-{company}.pdf"


def invoice_for_pdf(base):
  return invoice_queryset(base).select_related("purchase_order__goods_receipt")

@invoice_pdf_docs
class InvoicePdfApi(PDFView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    invoice = get_object_or_404(
      invoice_for_pdf(Invoice.objects.filter(business=request.business)), pk=pk
    )
    return pdf_response(pdf.invoice_pdf(invoice), invoice_filename(invoice))

@supplier_invoice_pdf_docs
class SupplierInvoicePdfApi(PDFView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    invoice = get_object_or_404(
      invoice_for_pdf(Invoice.objects.filter(supplier_profile=request.supplier)), pk=pk
    )
    return pdf_response(pdf.invoice_pdf(invoice), invoice_filename(invoice))

def po_filename(po, party):
  return f"{po.number}-{slugify(party) or 'order'}.pdf"

@po_pdf_docs
class PurchaseOrderPdfApi(PDFView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    po = get_object_or_404(
      po_queryset(PurchaseOrder.objects.filter(business=request.business)), pk=pk
    )
    return pdf_response(pdf.po_pdf(po), po_filename(po, po.supplier_profile.company_name))

@supplier_po_pdf_docs
class SupplierPurchaseOrderPdfApi(PDFView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    po = get_object_or_404(po_queryset(supplier_po_base(request.supplier)), pk=pk)
    return pdf_response(pdf.po_pdf(po), po_filename(po, po.business.business_name))

def grn_for_pdf(base):
  return grn_queryset(base).select_related(
    "business__owner__profile", "purchase_order__supplier_profile__user"
  )


def grn_filename(grn, party):
  return f"{grn.number}-{slugify(party) or 'receipt'}.pdf"

@grn_pdf_docs
class GoodsReceiptPdfApi(PDFView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    grn = get_object_or_404(
      grn_for_pdf(GoodsReceipt.objects.filter(business=request.business)), pk=pk
    )
    company = grn.purchase_order.supplier_profile.company_name
    return pdf_response(pdf.grn_pdf(grn, show_staff=True), grn_filename(grn, company))

@supplier_grn_pdf_docs
class SupplierGoodsReceiptPdfApi(PDFView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    grn = get_object_or_404(grn_for_pdf(supplier_grn_base(request.supplier)), pk=pk)
    return pdf_response(pdf.grn_pdf(grn), grn_filename(grn, grn.business.business_name))

@rfq_comparison_pdf_docs
class RFQComparisonPdfApi(PDFView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    rfq = get_object_or_404(
      RFQ.objects.select_related("business__owner__profile").prefetch_related("items"),
      pk=pk, business=request.business,
    )
    quotations = list(
      rfq.quotations.exclude(status=Quotation.Status.WITHDRAWN)
      .select_related("rfq", "supplier_profile", "recipient")
    )
    try:
      weights = parse_weights(request.query_params)
      ranked = rank_quotations(quotations, weights)
    except WeightError as err:
      return error_response(err.message, err.code, status=status.HTTP_400_BAD_REQUEST)

    by_price = request.query_params.get("sort") == "price"
    ordered = ranked
    if by_price:
      ordered = sorted(
        ranked, key=lambda r: (r["quotation"].grand_total, r["quotation"].submitted_at)
      )
    return pdf_response(
      pdf.comparison_pdf(rfq, ordered, weights, by_price), f"{rfq.number}-comparison.pdf"
    )
