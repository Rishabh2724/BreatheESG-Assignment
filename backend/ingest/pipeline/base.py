"""
Shared parsing primitives + the NormalizedRow contract every source parser emits.

The whole pipeline is: source bytes -> [ (line_no, raw_dict, NormalizedRow|None, error) ]
-> orchestrator persists RawRecord (always) + ActivityRecord (when normalized).
Keeping the contract tiny is deliberate: one shape to reason about, one place to test.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass
class NormalizedRow:
    """Source-agnostic intermediate. The orchestrator turns this into an ActivityRecord."""
    category: str                      # ActivityRecord.Category value
    scope: int                         # derived from category
    quantity: Optional[Decimal]        # the amount the emission factor multiplies
    unit: str                          # canonical unit (L, kWh, km, p-km, room-night, or currency)
    original_quantity: str = ""        # verbatim, before conversion
    original_unit: str = ""
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    facility_code: str = ""            # raw source code, resolved to Facility later
    # hints used only for emission-factor matching:
    fuel_type: str = ""                # diesel / natural_gas / short_haul / taxi ...
    region: str = ""                   # ISO country, for grid + hotel factors
    currency: str = ""                 # for spend-based goods
    extra_flags: list = field(default_factory=list)  # source-specific flags (e.g. distance estimated)


# Category -> Scope is fixed by the GHG Protocol; we encode it once here so no parser
# can disagree about which scope a category belongs to.
SCOPE_BY_CATEGORY = {
    "stationary_combustion": 1,
    "mobile_combustion": 1,
    "purchased_electricity": 2,
    "purchased_goods": 3,
    "business_travel_air": 3,
    "business_travel_hotel": 3,
    "business_travel_ground": 3,
}


def parse_decimal(raw) -> Optional[Decimal]:
    """Parse a number that may be German- or US-formatted.

    Handles '1.234,56' (de), '1,234.56' (us), '1234,56', '1234.56'. Heuristic: when both
    separators appear, whichever comes last is the decimal separator. When only a comma
    appears we treat it as the decimal separator (our sample data never uses bare-comma
    thousands). Returns None if unparseable — the caller decides whether that's fatal.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "")
    if s == "":
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):      # comma is decimal -> de
            s = s.replace(".", "").replace(",", ".")
        else:                                # dot is decimal -> us
            s = s.replace(",", "")
    elif has_comma:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


_DATE_FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y%m%d"]


def parse_date(raw) -> Optional[date]:
    """Parse a date across common SAP/portal/ISO formats. Day-first is preferred over
    month-first because our SAP/utility sources are European (DD.MM.YYYY dominant)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
