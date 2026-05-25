"""
Utility electricity parser.

Real-world shape we target: a CSV export from a utility's online portal (the way a
facilities team actually pulls this). Justification vs alternatives:
  - PDF bills: layout varies per utility, OCR/table-extraction is brittle and high-effort
    for low marginal signal in a prototype.
  - utility API: most utilities (especially outside the US/UK) expose no API at all.
A portal CSV is the realistic lowest common denominator. See SOURCES.md.

Nasties we handle:
  - billing periods that do NOT align to calendar months (kept native, never re-bucketed)
  - units in kWh OR MWh
  - meter IDs that resolve to a Facility (whose country sets the grid factor)
  - missing/blank consumption -> flagged, never assumed zero
"""

import csv
import io

from .base import NormalizedRow, parse_date, parse_decimal

HEADERS = {
    "meter": ["meter", "meter_id", "meter id", "mpan", "meter_no"],
    "site": ["site", "facility", "location", "plant"],
    "period_start": ["period_start", "billing_start", "billing period start", "start", "from"],
    "period_end": ["period_end", "billing_end", "billing period end", "end", "to"],
    "consumption": ["consumption", "usage", "kwh", "consumption_kwh", "energy"],
    "unit": ["unit", "uom"],
}

ENERGY_UNITS = {"kwh": ("kWh", 1), "mwh": ("kWh", 1000), "wh": ("kWh", 0.001)}


def _resolve_headers(fieldnames):
    lookup = {}
    lowered = {(h or "").strip().lower(): h for h in fieldnames}
    for canonical, aliases in HEADERS.items():
        for alias in aliases:
            if alias in lowered:
                lookup[canonical] = lowered[alias]
                break
    return lookup


def parse(content: bytes):
    text = content.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.splitlines() and ";" in text.splitlines()[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    cols = _resolve_headers(reader.fieldnames or [])

    for i, row in enumerate(reader, start=1):
        raw = {k: v for k, v in row.items()}
        try:
            if "consumption" not in cols:
                yield i, raw, None, "Could not locate a consumption/kWh column"
                continue

            qty_raw = row.get(cols.get("consumption", ""), "")
            unit_raw = (row.get(cols.get("unit", ""), "") or "").strip()
            qty = parse_decimal(qty_raw)
            unit_key = unit_raw.lower() or "kwh"  # portals often omit unit; kWh is the default
            if unit_key in ENERGY_UNITS:
                canon_unit, mult = ENERGY_UNITS[unit_key]
                qty = qty * parse_decimal(str(mult)) if qty is not None else None
            else:
                canon_unit = ""  # unknown energy unit -> flagged

            meter = (row.get(cols.get("meter", ""), "") or "").strip()
            site = (row.get(cols.get("site", ""), "") or "").strip()
            yield i, raw, NormalizedRow(
                category="purchased_electricity", scope=2,
                quantity=qty, unit=canon_unit,
                original_quantity=str(qty_raw), original_unit=unit_raw or "kWh",
                period_start=parse_date(row.get(cols.get("period_start", ""), "")),
                period_end=parse_date(row.get(cols.get("period_end", ""), "")),
                facility_code=site or meter,  # resolve by site, fall back to meter id
            ), ""
        except Exception as exc:
            yield i, raw, None, f"{type(exc).__name__}: {exc}"
