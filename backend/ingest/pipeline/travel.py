"""
Corporate travel parser (flights, hotels, ground).

Real-world shape we target: a JSON export shaped like a Concur/Navan trip feed — a list
of segments, each with a `type`. Justification: these platforms DO expose REST APIs
(Concur v3, Navan), but they need OAuth, partner approval, and a live tenant. The data
those APIs return is JSON, so we ingest the JSON export shape directly; swapping to a live
pull later is a transport change, not a model change. See SOURCES.md.

Nasties we handle:
  - flights give airport codes but often NOT distance -> derive via great-circle, flag it
  - three categories with three different emission bases (p-km, room-night, km)
  - unknown airport codes -> flagged, distance left null, co2e not computed

Emission basis per category (quantity = the number the factor multiplies):
  flight  -> quantity = distance_km * passengers, unit 'p-km', factor by haul (short/long)
  hotel   -> quantity = nights,                   unit 'room-night', factor by country
  ground  -> quantity = distance_km,              unit 'km', factor by mode
"""

import json
from decimal import Decimal

from .airports import haversine_km
from .base import NormalizedRow, parse_date

SHORT_HAUL_KM = 3700  # IATA-ish cut between short- and long-haul for factor selection


def _flight(seg):
    origin = (seg.get("origin") or seg.get("from") or "").upper()
    dest = (seg.get("destination") or seg.get("to") or "").upper()
    pax = int(seg.get("passengers", 1) or 1)
    dist = seg.get("distance_km")
    flags = []
    if dist in (None, "", 0):
        dist = haversine_km(origin, dest)
        if dist is not None:
            flags.append("DISTANCE_ESTIMATED")  # transparency: number was derived, not given
    if dist is None:
        # unknown airport(s) and no distance -> cannot compute; surface, don't guess
        return NormalizedRow(
            category="business_travel_air", scope=3, quantity=None, unit="p-km",
            original_quantity=f"{origin}->{dest} x{pax}", original_unit="route",
            period_start=parse_date(seg.get("date")), period_end=parse_date(seg.get("date")),
            fuel_type="short_haul", extra_flags=["UNMAPPED_CODE"],
        )
    dist = Decimal(str(dist))
    haul = "short_haul" if dist <= SHORT_HAUL_KM else "long_haul"
    return NormalizedRow(
        category="business_travel_air", scope=3,
        quantity=dist * pax, unit="p-km",
        original_quantity=f"{origin}->{dest} x{pax} ({dist} km)", original_unit="route",
        period_start=parse_date(seg.get("date")), period_end=parse_date(seg.get("date")),
        fuel_type=haul, extra_flags=flags,
    )


def _hotel(seg):
    nights = seg.get("nights")
    country = (seg.get("country") or "").upper()
    return NormalizedRow(
        category="business_travel_hotel", scope=3,
        quantity=Decimal(str(nights)) if nights not in (None, "") else None,
        unit="room-night",
        original_quantity=str(nights), original_unit="nights",
        period_start=parse_date(seg.get("check_in")), period_end=parse_date(seg.get("check_out")),
        region=country,
    )


def _ground(seg):
    dist = seg.get("distance_km")
    mode = (seg.get("mode") or "taxi").lower()
    return NormalizedRow(
        category="business_travel_ground", scope=3,
        quantity=Decimal(str(dist)) if dist not in (None, "") else None, unit="km",
        original_quantity=str(dist), original_unit="km",
        period_start=parse_date(seg.get("date")), period_end=parse_date(seg.get("date")),
        fuel_type=mode,
    )


_HANDLERS = {
    "flight": _flight, "air": _flight,
    "hotel": _hotel, "lodging": _hotel,
    "car": _ground, "ground": _ground, "rail": _ground, "train": _ground, "taxi": _ground,
}


def parse(content: bytes):
    try:
        data = json.loads(content.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        yield 1, {"_raw": content[:200].decode(errors="replace")}, None, f"Invalid JSON: {exc}"
        return
    segments = data.get("segments", data) if isinstance(data, dict) else data
    if not isinstance(segments, list):
        yield 1, {"_raw": str(data)[:200]}, None, "Expected a list of travel segments"
        return

    for i, seg in enumerate(segments, start=1):
        raw = dict(seg) if isinstance(seg, dict) else {"_raw": seg}
        try:
            stype = (seg.get("type") or "").lower()
            handler = _HANDLERS.get(stype)
            if not handler:
                yield i, raw, None, f"Unknown travel segment type: {stype!r}"
                continue
            yield i, raw, handler(seg), ""
        except Exception as exc:
            yield i, raw, None, f"{type(exc).__name__}: {exc}"
