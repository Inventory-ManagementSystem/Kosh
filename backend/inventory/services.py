from .models import Warehouse

def get_warehouse(business):
  warehouse, _ = Warehouse.objects.get_or_create(business=business)
  return warehouse