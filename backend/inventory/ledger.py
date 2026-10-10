from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from .models import (
    Product, StockMovement, DispatchItem, DispatchNote, Outlet, Warehouse,
)


@transaction.atomic
def record_movement(*, business, product_id, change, reason,
                    user=None, note="", dispatch_note=None):
  product = get_object_or_404(
    Product.objects.select_for_update(), pk=product_id, business=business
  )
  new_quantity = product.quantity + change
  if new_quantity < 0:
    raise ValidationError({"change": f"Insufficient stock for {product.name}."})

  product.quantity = new_quantity
  product.save(update_fields=["quantity", "updated_at"])

  return StockMovement.objects.create(
    business=business,
    product=product,
    quantity_change=change,
    balance_after=new_quantity,
    reason=reason,
    dispatch_note=dispatch_note,
    note=note,
    created_by=user,
  )

@transaction.atomic
def create_dispatch(*, business, outlet_id, items, user=None,
                    dispatch_date=None, notes=""):
  """
  items: list of {"product_id": UUID, "quantity": int}
  One dispatch note, one ledger row per item. All or nothing.
  """
  outlet = get_object_or_404(Outlet, pk=outlet_id, business=business, is_active=True)

  
  merged = {}
  for item in items:
    pid = item["product_id"]
    merged[pid] = merged.get(pid, 0) + item["quantity"]

 
  Warehouse.objects.select_for_update().get(business=business)
  count = DispatchNote.objects.filter(business=business).count()

  note = DispatchNote.objects.create(
    business=business,
    outlet=outlet,
    number=f"DN-{count + 1:04d}",
    notes=notes,
    created_by=user,
    **({"dispatch_date": dispatch_date} if dispatch_date else {}),
  )

  for product_id in sorted(merged, key=str):
    quantity = merged[product_id]
    DispatchItem.objects.create(
      dispatch_note=note, product_id=product_id, quantity=quantity
    )
    record_movement(
      business=business,
      product_id=product_id,
      change=-quantity,
      reason=StockMovement.Reason.DISPATCH,
      user=user,
      note=note.number,
      dispatch_note=note,
    )
  return note
