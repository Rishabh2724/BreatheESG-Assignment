# Sources

Per source: format I researched and chose, what's actually hard about it, what my sample file
looks like and why, what would break for real. Sample files in `backend/sample_data/`.

---

## 1. SAP — fuel & procurement → flat-file CSV upload

**Why CSV, not IDoc/BAPI/OData:** those need a live SAP system, credentials, and middleware. A
prototype can't stand that up, and the real handoff to an ESG vendor is a report export (ABAP
report, or MB51-style movements) as CSV/Excel anyway.

**What's hard (and handled):**
* semicolon-delimited, comma decimals (`1.250,50` = 1250.50) — German Excel locale
* German or English headers (`Werk`/plant, `Menge`/qty, `Einheit`/unit, `Betrag`/amount)
* `DD.MM.YYYY` dates
* plant codes (`DE01`) that mean nothing without a lookup → resolved to `Facility`, unresolved
  flagged `UNMAPPED_CODE`
* mixed fuel units (L / GAL / m³) normalized
* one file spans two scopes: fuel = Scope 1 combustion, everything else = Scope 3 spend

**Sample (`sap_fuel_procurement.csv`):** one row per behaviour — clean diesel (comma decimal),
gas in m³, gallons (conversion), EUR + INR procurement, unknown plant, negative correction,
unknown unit, a 150,000 L outlier.

**Breaks for real:** many more columns and inconsistent ordering between configs; "is this row
fuel?" isn't always answerable from a group code; real procurement needs category-level spend
factors + multi-currency/FX.

---

## 2. Utility — electricity → portal CSV export

**Why portal CSV:** PDF bill layouts vary per utility and parse badly; utility APIs barely
exist. A portal CSV is what a facilities team can actually produce anywhere.

**What's hard (and handled):**
* billing periods don't align to calendar months → stored as-is, never re-bucketed
* units vary (kWh / MWh) → normalized to kWh
* meter/site IDs resolve to a `Facility`; its country picks the grid factor (IN kWh ≠ DE kWh)
* blank consumption → flagged `MISSING_QTY`, never assumed zero

**Sample:** `utility_electricity.csv` has a month-straddling period, an MWh row, an Indian site,
an unknown site (falls back to global factor), a blank-consumption row. `utility_correction.csv`
re-sends one overlapping period as a second batch to demo `POSSIBLE_DUPLICATE`.

**Breaks for real:** real exports carry tariff blocks, day/night registers, demand charges;
meter-to-facility mapping gets messy; market-based Scope 2 (RECs/PPAs) not modeled.

---

## 3. Corporate travel → JSON (Concur/Navan-shaped trip feed)

**Why JSON:** Concur/Navan APIs need OAuth + a live tenant, but they return JSON segment lists.
I ingest that shape directly; a live pull later is a transport change, not a model change.

**What's hard (and handled):**
* distances often missing (only airport codes) → computed by great-circle, flagged
  `DISTANCE_ESTIMATED`; unknown airport → flagged `UNMAPPED_CODE`, no co2e
* three categories, three bases: flight per passenger-km (short/long haul), hotel per
  room-night (by country), ground per km (by mode) — all run through `quantity × factor`

**Sample (`travel.json`):** flight with no distance (estimated), long-haul with distance given,
flight to an unknown airport, two hotels in different countries, taxi + rail, and a
`helicopter` segment of unknown type that fails (proves the failed-row path).

**Breaks for real:** my airport table is ~13 codes (real needs full OurAirports ~75k); flight
factors should vary by cabin/aircraft/radiative forcing; ground is per-km (right for taxi,
approximate for rail, which is really passenger-km).

---

**Factors:** values in `seed.py` are in the right ballpark for published sources (DEFRA, IEA
grids, EEIO spend) but hand-entered and labelled illustrative — not for real reporting. Point
was a correct mechanism, not a factor library.
