"""
Orchestrator: turn an uploaded file/payload into RawRecords + ActivityRecords.

This is the one place that writes to the DB during ingestion. It is deliberately the only
component that knows about both the parsers and the models — parsers stay pure (bytes ->
NormalizedRow), persistence lives here.

Per source row:
  1. write a RawRecord (the receipt) ALWAYS
  2. if the row couldn't be normalized -> count as failed, stop (no canonical row)
  3. resolve facility, match factor, compute provisional co2e
  4. run validators -> flags; status = flagged if any flag else pending
  5. check for cross-source duplicates
  6. write the ActivityRecord + an 'ingest' AuditEvent
"""

from django.db import transaction
from django.db.models import Q

from ..models import ActivityRecord, AuditEvent, Facility, ImportBatch, RawRecord
from . import factors, sap, travel, utility, validate

PARSERS = {
    ImportBatch.Source.SAP: sap.parse,
    ImportBatch.Source.UTILITY: utility.parse,
    ImportBatch.Source.TRAVEL: travel.parse,
}


def _resolve_facility(org, code):
    if not code:
        return None
    return Facility.objects.filter(org=org, code=code).first()


def _duplicate_exists(org, batch, category, facility, period_start, period_end):
    """Same facility + category with an overlapping period in a DIFFERENT batch =
    likely the same activity arriving from two sources. We flag, never auto-merge."""
    if facility is None or period_start is None or period_end is None:
        return False
    return ActivityRecord.objects.filter(
        org=org, category=category, facility=facility,
    ).filter(
        Q(period_start__lte=period_end) & Q(period_end__gte=period_start)
    ).exclude(batch=batch).exists()


@transaction.atomic
def run_ingest(batch: ImportBatch, content: bytes, actor=None):
    """Ingest `content` into `batch`. Updates the batch tallies + status in place."""
    parser = PARSERS[batch.source_type]
    total = ok = flagged = failed = 0

    for line_no, raw_payload, normalized, error in parser(content):
        total += 1
        raw = RawRecord.objects.create(
            batch=batch, line_no=line_no, payload=raw_payload, parse_error=error or "",
        )
        if normalized is None:
            failed += 1
            continue

        facility = _resolve_facility(batch.org, normalized.facility_code)
        region = facility.country if facility else normalized.region
        factor = factors.match(
            category=normalized.category, fuel_type=normalized.fuel_type,
            region=region, currency=normalized.currency,
        )
        co2e = factors.compute_co2e(normalized.quantity, factor)

        flags = validate.flags_for(
            normalized, facility, factor,
            facility_code_given=bool(normalized.facility_code),
        )
        if _duplicate_exists(batch.org, batch, normalized.category, facility,
                             normalized.period_start, normalized.period_end):
            flags.append("POSSIBLE_DUPLICATE")

        status = (ActivityRecord.Status.FLAGGED if flags
                  else ActivityRecord.Status.PENDING)
        if status == ActivityRecord.Status.FLAGGED:
            flagged += 1
        else:
            ok += 1

        record = ActivityRecord.objects.create(
            org=batch.org, batch=batch, raw_record=raw, facility=facility,
            scope=normalized.scope, category=normalized.category,
            quantity=normalized.quantity, unit=normalized.unit,
            original_quantity=normalized.original_quantity,
            original_unit=normalized.original_unit,
            period_start=normalized.period_start, period_end=normalized.period_end,
            emission_factor=factor, co2e_kg=co2e, status=status, flags=flags,
        )
        AuditEvent.objects.create(
            record=record, actor=actor, action="ingest",
            field="", old_value="", new_value=f"{batch.source_type} line {line_no}",
        )

    batch.rows_total = total
    batch.rows_ok = ok
    batch.rows_flagged = flagged
    batch.rows_failed = failed
    batch.status = ImportBatch.Status.DONE
    batch.save()
    return batch
