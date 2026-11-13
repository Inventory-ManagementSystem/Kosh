from django.core.management.base import BaseCommand
from suppliers.geocoding import geocode_supplier
from suppliers.models import SupplierProfile


class Command(BaseCommand):
  help = "Fill map coordinates for supplier addresses that don't have them yet."
  def add_arguments(self, parser):
    parser.add_argument("--all", action="store_true", help="Re-geocode every supplier.")

  def handle(self, *args, **options):
    profiles = SupplierProfile.objects.all()
    if not options["all"]:
      profiles = profiles.filter(latitude__isnull=True)
    done = failed = 0
    for profile in profiles.iterator():
      if geocode_supplier(profile):
        done += 1
      else:
        failed += 1
        self.stdout.write(self.style.WARNING(f"Could not locate {profile.company_name}"))

    self.stdout.write(self.style.SUCCESS(f"Geocoded {done} supplier(s), {failed} failed."))