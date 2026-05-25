"""
Tests covering the invariants we'd be asked to defend:
  - source quirks normalize correctly (units, comma decimals, gallons, m3)
  - validators flag the right rows (and never silently fix data)
  - multi-tenancy actually isolates orgs
  - the audit lock is one-way and blocks edits
Run: python manage.py test ingest
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    ActivityRecord, EmissionFactor, Facility, ImportBatch, Organization, User,
)
from .pipeline.run import run_ingest
from .services import apply_edit, transition


def _factors():
    EmissionFactor.objects.create(category="mobile_combustion", fuel_type="diesel",
                                  factor_value=Decimal("2.68"), factor_unit="kgCO2e/L")
    EmissionFactor.objects.create(category="purchased_electricity", region="DE",
                                  factor_value=Decimal("0.38"), factor_unit="kgCO2e/kWh")
    EmissionFactor.objects.create(category="purchased_electricity", region="",
                                  factor_value=Decimal("0.45"), factor_unit="kgCO2e/kWh")


class SapNormalizationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="A", slug="a")
        Facility.objects.create(org=self.org, code="DE01", name="Munich", country="DE")
        _factors()

    def _ingest(self, csv_text):
        batch = ImportBatch.objects.create(org=self.org, source_type="SAP", filename="t.csv")
        run_ingest(batch, csv_text.encode())
        return batch

    def test_comma_decimal_and_co2e(self):
        csv = ("Buchungsdatum;Werk;Materialkurztext;Materialgruppe;Menge;Einheit;Betrag;Waehrung\n"
               "15.01.2026;DE01;Diesel;FUEL;1.250,50;L;;EUR\n")
        self._ingest(csv)
        r = ActivityRecord.objects.get()
        self.assertEqual(r.quantity, Decimal("1250.5000"))
        self.assertEqual(r.unit, "L")
        self.assertEqual(r.co2e_kg, Decimal("3351.340"))   # 1250.5 * 2.68
        self.assertEqual(r.scope, 1)
        self.assertEqual(r.status, "pending")

    def test_gallons_convert_to_litres(self):
        csv = ("Werk;Materialkurztext;Materialgruppe;Menge;Einheit\n"
               "DE01;Diesel;FUEL;100;GAL\n")
        self._ingest(csv)
        r = ActivityRecord.objects.get()
        self.assertAlmostEqual(float(r.quantity), 378.541, places=2)

    def test_negative_and_missing_unit_flagged_not_dropped(self):
        csv = ("Werk;Materialkurztext;Materialgruppe;Menge;Einheit\n"
               "DE01;Diesel;FUEL;-5;L\n"
               "DE01;Diesel;FUEL;10;XYZ\n")
        self._ingest(csv)
        flags = {tuple(r.flags) for r in ActivityRecord.objects.all()}
        self.assertIn(("NEGATIVE_QTY",), flags)
        self.assertIn(("MISSING_UNIT",), flags)
        self.assertEqual(ActivityRecord.objects.count(), 2)  # nothing dropped

    def test_unmapped_plant_code_flagged(self):
        csv = ("Werk;Materialkurztext;Materialgruppe;Menge;Einheit\n"
               "ZZ99;Diesel;FUEL;10;L\n")
        self._ingest(csv)
        self.assertIn("UNMAPPED_CODE", ActivityRecord.objects.get().flags)


class DuplicateDetectionTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="A", slug="a")
        Facility.objects.create(org=self.org, code="DE01", name="Munich", country="DE")
        _factors()

    def test_overlapping_period_across_batches_flags_duplicate(self):
        csv = ("Meter ID,Site,Billing Period Start,Billing Period End,Consumption,Unit\n"
               "M1,DE01,2026-01-01,2026-01-31,1000,kWh\n")
        for _ in range(2):
            b = ImportBatch.objects.create(org=self.org, source_type="UTILITY", filename="u.csv")
            run_ingest(b, csv.encode())
        dup = ActivityRecord.objects.filter(flags__contains=["POSSIBLE_DUPLICATE"])
        self.assertEqual(dup.count(), 1)  # second ingest flags, first does not


class TenancyTests(TestCase):
    def setUp(self):
        self.a = Organization.objects.create(name="A", slug="a")
        self.b = Organization.objects.create(name="B", slug="b")
        self.ua = User.objects.create_user("ua", password="x", org=self.a)
        self.ub = User.objects.create_user("ub", password="x", org=self.b)
        _factors()
        batch = ImportBatch.objects.create(org=self.a, source_type="UTILITY", filename="u.csv")
        run_ingest(batch, b"Meter ID,Site,Billing Period Start,Billing Period End,Consumption,Unit\n"
                          b"M1,X,2026-01-01,2026-01-31,1000,kWh\n")
        self.rec = ActivityRecord.objects.get()

    def test_other_org_cannot_read_record(self):
        c = APIClient(); c.force_authenticate(self.ub)
        self.assertEqual(c.get(f"/api/records/{self.rec.id}/").status_code, 404)

    def test_owner_can_read_record(self):
        c = APIClient(); c.force_authenticate(self.ua)
        self.assertEqual(c.get(f"/api/records/{self.rec.id}/").status_code, 200)

    def test_summary_only_counts_own_org(self):
        c = APIClient(); c.force_authenticate(self.ub)
        self.assertEqual(c.get("/api/summary/").json()["total_records"], 0)


class LockTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="A", slug="a")
        self.user = User.objects.create_user("u", password="x", org=self.org)
        _factors()
        Facility.objects.create(org=self.org, code="DE01", name="M", country="DE")
        b = ImportBatch.objects.create(org=self.org, source_type="UTILITY", filename="u.csv")
        run_ingest(b, b"Meter ID,Site,Billing Period Start,Billing Period End,Consumption,Unit\n"
                     b"M1,DE01,2026-01-01,2026-01-31,1000,kWh\n")
        self.rec = ActivityRecord.objects.get()

    def test_cannot_lock_unless_approved(self):
        with self.assertRaises(ValueError):
            transition(self.rec, "lock", self.user)

    def test_lock_is_one_way_and_blocks_edits(self):
        transition(self.rec, "approve", self.user)
        transition(self.rec, "lock", self.user)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.status, "locked")
        with self.assertRaises(ValueError):
            apply_edit(self.rec, {"quantity": "5"}, self.user)

    def test_edit_writes_audit_and_recomputes(self):
        transition(self.rec, "approve", self.user)  # approved, not locked
        apply_edit(self.rec, {"quantity": "2000"}, self.user)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.co2e_kg, Decimal("760.000"))  # 2000 * 0.38 (DE)
        self.assertTrue(self.rec.audit_events.filter(action="edit", field="quantity").exists())
        self.assertEqual(self.rec.edited_by, self.user)
