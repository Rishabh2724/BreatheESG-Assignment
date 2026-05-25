"""
Data model for Breathe ESG ingestion prototype.

Design spine: TWO LAYERS.
  RawRecord  = the exact bytes a source handed us, never mutated. The audit anchor.
  ActivityRecord = the normalized, reviewable, carbon-bearing row, derived from a RawRecord.

Every canonical row points back to the raw row it came from. That single link is what
gives us "which source produced this, when, was it edited" structurally rather than by
convention. Everything else (multi-tenancy, scope, audit) hangs off that.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #
class Organization(models.Model):
    """Tenant root. Every business row carries org_id; querysets are scoped by it.

    We do NOT use schema-per-tenant or separate databases. For a prototype that is
    over-engineering: a single FK + disciplined query scoping demonstrates the model
    handles multi-tenancy without the operational weight. Documented in MODEL.md.
    """
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Custom user so we can attach an org and a coarse role from day one.

    Roles are intentionally coarse (analyst / admin). Fine-grained RBAC is a documented
    non-goal — see TRADEOFFS.md.
    """
    class Role(models.TextChoices):
        ANALYST = "analyst", "Analyst"
        ADMIN = "admin", "Admin"

    org = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="users"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ANALYST)

    def __str__(self):
        return self.username


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
class Facility(models.Model):
    """A physical site. The lookup table SAP plant codes and utility meters resolve to.

    "Plant codes mean nothing without a lookup table" — this is that table. A raw SAP row
    carries an opaque code like 'DE01'; we resolve it here to a name + country. Country
    matters because the electricity grid emission factor is region-specific.
    """
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="facilities")
    code = models.CharField(max_length=50, help_text="Source-native code, e.g. SAP plant 'DE01'")
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=2, help_text="ISO-3166 alpha-2, drives grid factor")

    class Meta:
        unique_together = ("org", "code")
        verbose_name_plural = "facilities"

    def __str__(self):
        return f"{self.code} — {self.name}"


class EmissionFactor(models.Model):
    """A single conversion factor: activity quantity -> kgCO2e.

    Kept deliberately flat. Real factor databases (DEFRA, EPA, IEA, ecoinvent) version
    factors by year, methodology, and geography. We seed a small representative set and
    match by (category, region, fuel_type). A full versioned factor service is a
    documented non-goal (TRADEOFFS.md) — but valid_from is here so the shape supports it.
    """
    category = models.CharField(max_length=40)
    region = models.CharField(max_length=2, blank=True, help_text="ISO country, blank = global")
    fuel_type = models.CharField(max_length=40, blank=True, help_text="diesel, natural_gas, ...")
    factor_value = models.DecimalField(max_digits=14, decimal_places=6)
    factor_unit = models.CharField(max_length=40, help_text="e.g. kgCO2e/L, kgCO2e/kWh, kgCO2e/EUR")
    currency = models.CharField(max_length=3, blank=True, help_text="set for spend-based factors")
    valid_from = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=120, help_text="provenance, e.g. 'DEFRA 2024'")

    def __str__(self):
        return f"{self.category}/{self.fuel_type or self.region or 'global'} = {self.factor_value} {self.factor_unit}"


# --------------------------------------------------------------------------- #
# Ingestion: raw layer
# --------------------------------------------------------------------------- #
class ImportBatch(models.Model):
    """One ingestion event — one uploaded file or one API pull.

    Carries the source_type and the running tally the dashboard shows
    ("12 ok / 3 flagged / 1 failed"). Nothing carbon-bearing lives here; it's the envelope.
    """
    class Source(models.TextChoices):
        SAP = "SAP", "SAP (fuel & procurement)"
        UTILITY = "UTILITY", "Utility (electricity)"
        TRAVEL = "TRAVEL", "Corporate travel"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="batches")
    source_type = models.CharField(max_length=10, choices=Source.choices)
    filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    rows_total = models.IntegerField(default=0)
    rows_ok = models.IntegerField(default=0)
    rows_flagged = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source_type} {self.filename} ({self.created_at:%Y-%m-%d})"


class RawRecord(models.Model):
    """The receipt. Exactly what one source line contained, parsed to JSON, never mutated.

    Created for EVERY line — even ones we can't normalize. If normalization fails entirely,
    parse_error is set and no ActivityRecord is produced (that's a "failed" row). If it
    succeeds, an ActivityRecord points back here. This is the audit anchor: an auditor can
    always see the original alongside the number we derived.
    """
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="raw_records")
    line_no = models.IntegerField(help_text="1-based position in the source file")
    payload = models.JSONField(help_text="original row, original headers, original units, verbatim")
    parse_error = models.TextField(blank=True, help_text="set when the line could not be normalized")

    class Meta:
        ordering = ["line_no"]

    def __str__(self):
        return f"{self.batch_id}:{self.line_no}"


# --------------------------------------------------------------------------- #
# Ingestion: canonical layer
# --------------------------------------------------------------------------- #
class ActivityRecord(models.Model):
    """The normalized, reviewable row. The single editable surface an analyst sees.

    quantity/unit are canonical (L, kWh, km, room-night, or a currency amount for
    spend-based procurement). original_quantity/original_unit preserve what the raw row
    said BEFORE conversion, so the analyst can see the transform without joining to raw.

    co2e_kg is computed at ingest (analysts must see a number to sanity-check it) but is
    PROVISIONAL until the row is locked. scope is derived from category but stored so it
    can be overridden — and any override is written to AuditEvent.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        FLAGGED = "flagged", "Flagged"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        LOCKED = "locked", "Locked (audit-sealed)"

    # Category -> scope is deterministic at ingest; see ingestion/normalize.py
    class Category(models.TextChoices):
        STATIONARY_COMBUSTION = "stationary_combustion", "Stationary combustion"   # Scope 1
        MOBILE_COMBUSTION = "mobile_combustion", "Mobile combustion"               # Scope 1
        PURCHASED_ELECTRICITY = "purchased_electricity", "Purchased electricity"   # Scope 2
        PURCHASED_GOODS = "purchased_goods", "Purchased goods & services"          # Scope 3
        BUSINESS_TRAVEL_AIR = "business_travel_air", "Business travel — air"       # Scope 3
        BUSINESS_TRAVEL_HOTEL = "business_travel_hotel", "Business travel — hotel" # Scope 3
        BUSINESS_TRAVEL_GROUND = "business_travel_ground", "Business travel — ground"  # Scope 3

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="activity")
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="activity")
    raw_record = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name="activity")
    facility = models.ForeignKey(Facility, null=True, blank=True, on_delete=models.SET_NULL)

    scope = models.IntegerField(choices=[(1, "Scope 1"), (2, "Scope 2"), (3, "Scope 3")])
    category = models.CharField(max_length=40, choices=Category.choices)

    quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True, help_text="canonical unit")
    original_quantity = models.CharField(max_length=60, blank=True, help_text="verbatim from raw")
    original_unit = models.CharField(max_length=40, blank=True, help_text="verbatim from raw")

    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True, help_text="kept native; not month-aligned")

    emission_factor = models.ForeignKey(EmissionFactor, null=True, blank=True, on_delete=models.SET_NULL)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True,
                                  help_text="provisional until status=locked")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    flags = models.JSONField(default=list, blank=True,
                             help_text="e.g. ['MISSING_UNIT','OUTLIER','POSSIBLE_DUPLICATE']")

    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.SET_NULL)
    edited_at = models.DateTimeField(null=True, blank=True, help_text="null = untouched by a human")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]

    @property
    def is_locked(self):
        return self.status == self.Status.LOCKED

    def __str__(self):
        return f"{self.category} {self.quantity}{self.unit} [{self.status}]"


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
class AuditEvent(models.Model):
    """Append-only history. Never updated, never deleted.

    Every state change an analyst makes — edit a value, approve, reject, lock — writes one
    row here capturing actor, field, old, new. This is the audit trail an auditor reviews
    and the answer to "was this row edited, by whom, when".
    """
    record = models.ForeignKey(ActivityRecord, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40, help_text="edit | approve | reject | lock | ingest")
    field = models.CharField(max_length=60, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} on {self.record_id} by {self.actor_id}"
