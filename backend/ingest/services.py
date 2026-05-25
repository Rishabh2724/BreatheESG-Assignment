"""
Review-side business logic: editing, recompute, and the state transitions an analyst
drives. Kept out of views so the rules (what's lockable, what recompute means, what gets
audited) live in one readable place.
"""

from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import ActivityRecord, AuditEvent
from .pipeline import validate
from .pipeline.base import parse_date


def _coerce(field, value):
    """PATCH payloads arrive as strings/ids; cast each editable field to its model type.

    `facility` is resolved to an instance by the view before it reaches here, so it's
    passed through untouched."""
    if value in ("", None) and field in ("quantity", "period_start", "period_end"):
        return None
    if field == "quantity":
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"quantity '{value}' is not a number")
    if field == "scope":
        return int(value)
    if field in ("period_start", "period_end"):
        return parse_date(value)
    return value

# Fields an analyst may correct on a canonical row. Provenance (raw_record, batch, source)
# is intentionally NOT editable — you fix the interpretation, never the receipt.
EDITABLE_FIELDS = {
    "quantity", "unit", "scope", "category",
    "facility", "period_start", "period_end",
}

# Flags that describe the SOURCE, not the current values. We preserve these across edits
# (an estimated distance stays estimated; a cross-source dup stays a dup) — except
# UNMAPPED_CODE, which an analyst can resolve by assigning a facility.
PROVENANCE_FLAGS = {"DISTANCE_ESTIMATED", "POSSIBLE_DUPLICATE"}


def _recompute(record: ActivityRecord):
    """Recompute provisional co2e and value-based flags after an edit.

    co2e is recomputed against the row's EXISTING emission factor (quantity * factor) — we
    do not silently re-pick a factor on edit; changing the factor is a deliberate, separate
    concern. Flags are rebuilt from current values, preserving source-level flags.
    """
    if record.quantity is not None and record.emission_factor is not None:
        record.co2e_kg = (record.quantity * record.emission_factor.factor_value).quantize(
            Decimal("0.001"))
    else:
        record.co2e_kg = None

    kept = [f for f in record.flags if f in PROVENANCE_FLAGS]
    if record.facility is None and "UNMAPPED_CODE" in record.flags:
        kept.append("UNMAPPED_CODE")  # still unresolved

    value_flags = []
    if record.quantity is None:
        value_flags.append("MISSING_QTY")
    elif record.quantity < 0:
        value_flags.append("NEGATIVE_QTY")
    if record.category not in validate.SPEND_CATEGORIES and not record.unit:
        value_flags.append("MISSING_UNIT")
    if record.emission_factor is None:
        value_flags.append("NO_FACTOR")
    ceiling = validate.OUTLIER_CEILINGS.get(record.unit)
    if record.quantity is not None and ceiling is not None and record.quantity > ceiling:
        value_flags.append("OUTLIER")

    record.flags = list(dict.fromkeys(kept + value_flags))


def apply_edit(record: ActivityRecord, changes: dict, actor):
    """Apply field edits, recompute, write one AuditEvent per changed field.

    Raises ValueError if the row is locked. Returns the record."""
    if record.is_locked:
        raise ValueError("Locked rows are audit-sealed and cannot be edited.")

    events = []
    for field, raw_value in changes.items():
        if field not in EDITABLE_FIELDS:
            continue
        new_value = _coerce(field, raw_value)
        old_value = getattr(record, field)
        if str(old_value) == str(new_value):
            continue
        setattr(record, field, new_value)
        events.append(AuditEvent(
            record=record, actor=actor, action="edit", field=field,
            old_value=str(old_value), new_value=str(new_value)))

    if not events:
        return record  # nothing actually changed

    _recompute(record)
    record.edited_by = actor
    record.edited_at = timezone.now()
    # If edits cleared every flag, drop back to pending; otherwise stay flagged.
    if record.status in (ActivityRecord.Status.PENDING, ActivityRecord.Status.FLAGGED):
        record.status = (ActivityRecord.Status.FLAGGED if record.flags
                         else ActivityRecord.Status.PENDING)
    record.save()
    AuditEvent.objects.bulk_create(events)
    return record


def transition(record: ActivityRecord, action: str, actor):
    """approve / reject / lock. Enforces the one-way lock and legal transitions."""
    S = ActivityRecord.Status
    old = record.status

    if action == "approve":
        if record.is_locked:
            raise ValueError("Row is locked.")
        record.status = S.APPROVED
    elif action == "reject":
        if record.is_locked:
            raise ValueError("Row is locked.")
        record.status = S.REJECTED
    elif action == "lock":
        if record.status != S.APPROVED:
            raise ValueError("Only approved rows can be locked.")
        record.status = S.LOCKED
    else:
        raise ValueError(f"Unknown action: {action}")

    record.save(update_fields=["status"])
    AuditEvent.objects.create(
        record=record, actor=actor, action=action, field="status",
        old_value=old, new_value=record.status)
    return record
