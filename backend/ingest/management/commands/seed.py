"""
Seed a demo tenant with users, the facility lookup, emission factors, and three ingested
batches built from the sample files. Idempotent-ish: pass --fresh to wipe ingest data first.

Run: python manage.py seed --fresh
"""

from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from ingest.models import (
    ActivityRecord, AuditEvent, EmissionFactor, Facility, ImportBatch,
    Organization, RawRecord, User,
)
from ingest.pipeline.run import run_ingest

SAMPLE_DIR = Path(__file__).resolve().parents[3] / "sample_data"

# Illustrative factors. Values are representative (DEFRA 2024 / IEA grid intensities) but
# fabricated for the prototype — NOT an authoritative factor set. (category, region,
# fuel_type, value, unit, currency, source)
FACTORS = [
    ("mobile_combustion", "", "diesel", "2.68", "kgCO2e/L", "", "DEFRA 2024 (illustrative)"),
    ("mobile_combustion", "", "petrol", "2.31", "kgCO2e/L", "", "DEFRA 2024 (illustrative)"),
    ("stationary_combustion", "", "natural_gas", "2.02", "kgCO2e/m3", "", "DEFRA 2024 (illustrative)"),
    ("purchased_electricity", "DE", "", "0.380", "kgCO2e/kWh", "", "IEA 2023 grid (illustrative)"),
    ("purchased_electricity", "IN", "", "0.710", "kgCO2e/kWh", "", "IEA 2023 grid (illustrative)"),
    ("purchased_electricity", "", "", "0.450", "kgCO2e/kWh", "", "global avg (illustrative)"),
    ("purchased_goods", "", "", "0.300", "kgCO2e/EUR", "EUR", "EEIO spend-based (illustrative)"),
    ("purchased_goods", "", "", "0.050", "kgCO2e/INR", "INR", "EEIO spend-based (illustrative)"),
    ("purchased_goods", "", "", "0.250", "kgCO2e/EUR", "", "EEIO global (illustrative)"),
    ("business_travel_air", "", "short_haul", "0.158", "kgCO2e/p-km", "", "DEFRA 2024 (illustrative)"),
    ("business_travel_air", "", "long_haul", "0.150", "kgCO2e/p-km", "", "DEFRA 2024 (illustrative)"),
    ("business_travel_hotel", "IN", "", "24.0", "kgCO2e/room-night", "", "DEFRA 2024 (illustrative)"),
    ("business_travel_hotel", "US", "", "16.0", "kgCO2e/room-night", "", "DEFRA 2024 (illustrative)"),
    ("business_travel_hotel", "", "", "20.0", "kgCO2e/room-night", "", "global avg (illustrative)"),
    ("business_travel_ground", "", "taxi", "0.170", "kgCO2e/km", "", "DEFRA 2024 (illustrative)"),
    ("business_travel_ground", "", "rail", "0.035", "kgCO2e/km", "", "DEFRA 2024 (illustrative)"),
]

FACILITIES = [
    ("DE01", "Munich Plant", "DE"),
    ("DE02", "Hamburg Warehouse", "DE"),
    ("IN01", "Pune Office", "IN"),
]


class Command(BaseCommand):
    help = "Seed a demo org with users, factors, facilities, and three ingested batches."

    def add_arguments(self, parser):
        parser.add_argument("--fresh", action="store_true",
                            help="Delete existing ingest data before seeding")

    def handle(self, *args, **opts):
        if opts["fresh"]:
            AuditEvent.objects.all().delete()
            ActivityRecord.objects.all().delete()
            RawRecord.objects.all().delete()
            ImportBatch.objects.all().delete()
            self.stdout.write("Wiped existing batches/records.")

        org, _ = Organization.objects.get_or_create(slug="acme", defaults={"name": "Acme Corp"})

        analyst = self._user("analyst", "analyst123", User.Role.ANALYST, org)
        admin = self._user("admin", "admin123", User.Role.ADMIN, org, superuser=True)

        for code, name, country in FACILITIES:
            Facility.objects.get_or_create(org=org, code=code,
                                           defaults={"name": name, "country": country})

        EmissionFactor.objects.all().delete()
        for cat, region, fuel, val, unit, cur, src in FACTORS:
            EmissionFactor.objects.create(
                category=cat, region=region, fuel_type=fuel,
                factor_value=Decimal(val), factor_unit=unit, currency=cur,
                valid_from="2024-01-01", source=src,
            )

        self._fresh = opts["fresh"]
        self._ingest(org, analyst, ImportBatch.Source.SAP, "sap_fuel_procurement.csv")
        self._ingest(org, analyst, ImportBatch.Source.UTILITY, "utility_electricity.csv")
        self._ingest(org, analyst, ImportBatch.Source.UTILITY, "utility_correction.csv")
        self._ingest(org, analyst, ImportBatch.Source.TRAVEL, "travel.json")

        self.stdout.write(self.style.SUCCESS(
            f"\nSeed complete. Org={org.name}\n"
            f"  analyst / analyst123  token={Token.objects.get(user=analyst).key}\n"
            f"  admin   / admin123    token={Token.objects.get(user=admin).key}"
        ))

    def _user(self, username, password, role, org, superuser=False):
        u, created = User.objects.get_or_create(
            username=username, defaults={"role": role, "org": org, "is_staff": superuser,
                                         "is_superuser": superuser})
        if created:
            u.set_password(password)
            u.org, u.role, u.is_staff, u.is_superuser = org, role, superuser, superuser
            u.save()
        Token.objects.get_or_create(user=u)
        return u

    def _ingest(self, org, actor, source, filename):
        # Redeploy-safe: don't re-ingest a file already loaded (avoids duplicate batches
        # when `seed` runs on every deploy). --fresh forces a clean reload.
        if not getattr(self, "_fresh", False) and \
                ImportBatch.objects.filter(org=org, filename=filename).exists():
            self.stdout.write(f"  {source:8} {filename:28} -> already present, skipped")
            return
        content = (SAMPLE_DIR / filename).read_bytes()
        batch = ImportBatch.objects.create(
            org=org, source_type=source, filename=filename, uploaded_by=actor)
        run_ingest(batch, content, actor=actor)
        self.stdout.write(
            f"  {source:8} {filename:28} -> total={batch.rows_total} "
            f"ok={batch.rows_ok} flagged={batch.rows_flagged} failed={batch.rows_failed}")
