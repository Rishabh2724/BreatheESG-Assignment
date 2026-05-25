"""
SAP fuel + procurement parser.

Real-world shape we target: a flat-file CSV export from a movements/postings report
(think an ABAP report or MB51-style dump), NOT IDoc/BAPI/OData. Justification: a live
SAP connector needs a real SAP system, RFC/OData credentials, and middleware — none of
which a prototype can stand up. A CSV/Excel handoff from the client's SAP team is the
single most common way this data actually reaches an ESG vendor. See SOURCES.md.

Nasties we deliberately handle (because they are the norm, not the exception):
  - semicolon delimiter (German Excel locale)
  - comma decimal separators ('1.234,56')
  - German OR English headers (Werk/plant, Menge/quantity, ...)
  - DD.MM.YYYY dates
  - opaque plant codes that mean nothing without the Facility lookup
  - mixed units for fuel (L / Liter / LTR / GAL)
  - one file carrying BOTH Scope 1 fuel and Scope 3 procurement rows

Classification: a row is fuel (Scope 1) when its material group is 'FUEL' (or the material
text names a known fuel); otherwise it is treated as procurement spend (Scope 3), valued
by amount + currency. This split is why one SAP file spans two scopes.
"""

import csv
import io

from .base import SCOPE_BY_CATEGORY, NormalizedRow, parse_date, parse_decimal

# Header aliases: canonical_key -> accepted source headers (German + English).
HEADERS = {
    "posting_date": ["posting_date", "buchungsdatum", "posting date", "datum"],
    "plant": ["plant", "werk", "plant_code"],
    "material": ["material", "material_no", "matnr"],
    "material_text": ["material_text", "materialkurztext", "description", "bezeichnung"],
    "material_group": ["material_group", "materialgruppe", "matkl", "group"],
    "quantity": ["quantity", "menge", "qty"],
    "unit": ["unit", "einheit", "basisme", "uom", "meins"],
    "amount": ["amount", "betrag", "wert", "value"],
    "currency": ["currency", "waehrung", "währung", "waers"],
}

# Fuel material text -> (category, fuel_type). Natural gas burns on-site (stationary);
# diesel/petrol in our sample is fleet (mobile). Documented assumption in SOURCES.md.
FUEL_MAP = {
    "diesel": ("mobile_combustion", "diesel"),
    "petrol": ("mobile_combustion", "petrol"),
    "gasoline": ("mobile_combustion", "petrol"),
    "benzin": ("mobile_combustion", "petrol"),
    "natural gas": ("stationary_combustion", "natural_gas"),
    "erdgas": ("stationary_combustion", "natural_gas"),
    "lng": ("stationary_combustion", "natural_gas"),
}

# Volume unit -> (canonical_unit, multiplier_to_canonical)
VOLUME_UNITS = {
    "l": ("L", 1), "ltr": ("L", 1), "liter": ("L", 1), "litre": ("L", 1), "liters": ("L", 1),
    "gal": ("L", 3.78541), "gallon": ("L", 3.78541),
    # Natural gas is metered in m3 and kept in m3 — converting gas volume to "litres" and
    # applying a litre factor would be dimensionally wrong. Its factor is kgCO2e/m3.
    "m3": ("m3", 1), "cbm": ("m3", 1),
}


def _resolve_headers(fieldnames):
    """Map the file's actual headers onto our canonical keys, case-insensitively."""
    lookup = {}
    lowered = {(h or "").strip().lower(): h for h in fieldnames}
    for canonical, aliases in HEADERS.items():
        for alias in aliases:
            if alias in lowered:
                lookup[canonical] = lowered[alias]
                break
    return lookup


def _classify(material_text, material_group):
    """Return (category, fuel_type) — fuel rows when group/text says fuel, else procurement."""
    mt = (material_text or "").lower()
    if (material_group or "").strip().upper() == "FUEL":
        for key, val in FUEL_MAP.items():
            if key in mt:
                return val
        return ("mobile_combustion", "diesel")  # group says fuel but text unclear -> default
    for key, val in FUEL_MAP.items():
        if key in mt:
            return val
    return ("purchased_goods", "")  # everything else is procurement spend


def parse(content: bytes):
    """Yield (line_no, raw_dict, NormalizedRow|None, error) for each data row."""
    text = content.decode("utf-8-sig", errors="replace")
    # SAP German exports use ';'; sniff but default to ';' then ','.
    delimiter = ";" if text.splitlines() and ";" in text.splitlines()[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    cols = _resolve_headers(reader.fieldnames or [])

    for i, row in enumerate(reader, start=1):
        raw = {k: v for k, v in row.items()}
        try:
            if "quantity" not in cols and "amount" not in cols:
                yield i, raw, None, "Could not locate quantity or amount column"
                continue

            material_text = row.get(cols.get("material_text", ""), "")
            material_group = row.get(cols.get("material_group", ""), "")
            category, fuel_type = _classify(material_text, material_group)
            scope = SCOPE_BY_CATEGORY[category]
            plant = (row.get(cols.get("plant", ""), "") or "").strip()
            pdate = parse_date(row.get(cols.get("posting_date", ""), ""))

            if category == "purchased_goods":
                amount = parse_decimal(row.get(cols.get("amount", ""), ""))
                currency = (row.get(cols.get("currency", ""), "") or "").strip().upper()
                yield i, raw, NormalizedRow(
                    category=category, scope=scope, quantity=amount, unit=currency,
                    original_quantity=str(row.get(cols.get("amount", ""), "")),
                    original_unit=currency, period_start=pdate, period_end=pdate,
                    facility_code=plant, currency=currency,
                ), ""
            else:
                qty_raw = row.get(cols.get("quantity", ""), "")
                unit_raw = (row.get(cols.get("unit", ""), "") or "").strip()
                qty = parse_decimal(qty_raw)
                unit_key = unit_raw.lower()
                if unit_key in VOLUME_UNITS:
                    canon_unit, mult = VOLUME_UNITS[unit_key]
                    qty = qty * parse_decimal(str(mult)) if qty is not None else None
                else:
                    canon_unit = ""  # unknown unit -> validator will flag, co2e stays null
                yield i, raw, NormalizedRow(
                    category=category, scope=scope, quantity=qty, unit=canon_unit,
                    original_quantity=str(qty_raw), original_unit=unit_raw,
                    period_start=pdate, period_end=pdate,
                    facility_code=plant, fuel_type=fuel_type,
                ), ""
        except Exception as exc:  # one bad row must not kill the batch
            yield i, raw, None, f"{type(exc).__name__}: {exc}"
