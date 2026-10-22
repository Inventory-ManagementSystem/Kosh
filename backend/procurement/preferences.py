from .models import ProcurementSettings

def get_procurement_settings(business):
  settings, _ = ProcurementSettings.objects.get_or_create(business=business)
  return settings
