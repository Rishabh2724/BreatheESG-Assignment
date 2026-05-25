"""
Minimal airport coordinate lookup + great-circle distance.

Travel platforms frequently give you airport codes but NOT distance. Rather than fail,
we derive distance from coordinates. This is a small hand-picked set covering the routes
in our sample data; a real deployment would back this with the full OurAirports dataset
(~75k rows). Unknown codes return None and the row gets flagged, never guessed.
"""

from math import asin, cos, radians, sin, sqrt
from typing import Optional

# IATA -> (lat, lon)
AIRPORTS = {
    "BOM": (19.0887, 72.8679),   # Mumbai
    "DEL": (28.5562, 77.1000),   # Delhi
    "BLR": (13.1986, 77.7066),   # Bengaluru
    "MAA": (12.9941, 80.1709),   # Chennai
    "LHR": (51.4700, -0.4543),   # London Heathrow
    "CDG": (49.0097, 2.5479),    # Paris CDG
    "FRA": (50.0379, 8.5622),    # Frankfurt
    "JFK": (40.6413, -73.7781),  # New York JFK
    "SFO": (37.6213, -122.3790), # San Francisco
    "SIN": (1.3644, 103.9915),   # Singapore
    "DXB": (25.2532, 55.3657),   # Dubai
    "HKG": (22.3080, 113.9185),  # Hong Kong
    "SYD": (-33.9399, 151.1753), # Sydney
}


def haversine_km(a: str, b: str) -> Optional[float]:
    """Great-circle distance in km between two IATA codes, or None if either is unknown."""
    pa, pb = AIRPORTS.get(a.upper()), AIRPORTS.get(b.upper())
    if not pa or not pb:
        return None
    lat1, lon1 = radians(pa[0]), radians(pa[1])
    lat2, lon2 = radians(pb[0]), radians(pb[1])
    d = 2 * asin(sqrt(sin((lat2 - lat1) / 2) ** 2
                      + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2))
    return round(6371.0 * d, 1)
