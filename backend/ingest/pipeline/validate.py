"""
Validation rules -> flags.

Philosophy: flags surface judgement calls to a human; they never silently fix data. A
flagged row is still ingested and still reviewable — we just don't pretend it's clean.
Thresholds here are intentionally simple static bounds; a real system would use rolling
statistical baselines per facility (documented in TRADEOFFS.md).
"""

from decimal import Decimal

# Per-canonical-unit "this is implausibly large for one row" ceilings.
OUTLIER_CEILINGS = {
    "L": Decimal("100000"),
    "m3": Decimal("50000"),
    "kWh": Decimal("5000000"),
    "p-km": Decimal("200000"),
    "room-night": Decimal("365"),
    "km": Decimal("10000"),
}

# Categories valued by spend — a blank "unit" there is a currency, not a missing unit.
SPEND_CATEGORIES = {"purchased_goods"}


def flags_for(normalized, facility, factor, facility_code_given) -> list:
    """Compute the flag list for one normalized row. `normalized` is a NormalizedRow."""
    flags = list(normalized.extra_flags)  # parser-supplied flags (e.g. DISTANCE_ESTIMATED)

    qty = normalized.quantity
    if qty is None:
        flags.append("MISSING_QTY")
    elif qty < 0:
        flags.append("NEGATIVE_QTY")

    if normalized.category not in SPEND_CATEGORIES and not normalized.unit:
        flags.append("MISSING_UNIT")

    if facility_code_given and facility is None:
        flags.append("UNMAPPED_CODE")  # had a code, no Facility row resolves it

    if factor is None:
        flags.append("NO_FACTOR")

    ceiling = OUTLIER_CEILINGS.get(normalized.unit)
    if qty is not None and ceiling is not None and qty > ceiling:
        flags.append("OUTLIER")

    return list(dict.fromkeys(flags))  # dedupe, preserve order
