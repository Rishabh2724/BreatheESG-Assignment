"""
Emission-factor matching and co2e computation.

co2e is uniform across every category: co2e_kg = quantity * factor_value. The parsers do
the work of making `quantity` the right thing (litres, kWh, passenger-km, room-nights,
spend) so this stays a single multiply. Matching falls back from specific to global so a
missing regional factor degrades gracefully instead of dropping the row.
"""

from decimal import Decimal
from typing import Optional

from ..models import EmissionFactor


def match(category: str, fuel_type: str = "", region: str = "",
          currency: str = "") -> Optional[EmissionFactor]:
    """Pick the factor for a normalized row, deterministically.

    fuel_type and currency are the discriminators that MUST match exactly (a diesel row
    must never get a petrol factor). region is the only dimension we relax: if there's no
    factor for the row's country we fall back to the region-agnostic ('') global factor.
    This avoids the trap of a blank/unknown region silently grabbing some other country's
    grid factor. Returns None when nothing matches — the row is then flagged NO_FACTOR.
    """
    base = EmissionFactor.objects.filter(
        category=category, fuel_type=fuel_type, currency=currency)

    f = base.filter(region=region).order_by("-valid_from").first()
    if f:
        return f
    if region:  # region-specific miss -> try the global ('' region) factor
        return base.filter(region="").order_by("-valid_from").first()
    return None


def compute_co2e(quantity: Optional[Decimal], factor: Optional[EmissionFactor]):
    """Return provisional kgCO2e, or None when we lack a quantity or a factor."""
    if quantity is None or factor is None:
        return None
    return (quantity * factor.factor_value).quantize(Decimal("0.001"))
