# Sources

For each of the three source types: the real-world format I researched, what I learned,
what my fabricated sample data looks like and why, and what would break in a real
deployment. Sample files live in `backend/sample_data/`.

---

## 1. SAP — fuel & procurement

**Ingestion mechanism chosen: flat-file CSV upload.**

### Real-world format
SAP can expose data as IDoc, BAPI/RFC, or OData services. I deliberately did **not** target
those. Every one of them needs a live SAP system, RFC/OData credentials, and usually
middleware (PI/PO, CPI) sitting in front. A prototype cannot stand that up, and more
importantly it is not how this data usually reaches an ESG vendor in the first place: the
client's SAP team runs a report (an ABAP report, or a transaction like MB51 for material
movements) and hands over a CSV/Excel export. That export is the realistic lowest common
denominator, so that's what I ingest.

### What I learned (and handle)
SAP exports configured for a German locale are genuinely hostile:
- **Semicolon-delimited** (German Excel uses `;` because `,` is the decimal separator).
- **Comma decimals**: `1.250,50` means 1250.50. My parser detects de- vs us-formatting by
  which separator comes last.
- **German or English headers**: `Werk`/plant, `Menge`/quantity, `Einheit`/unit,
  `Betrag`/amount, `Währung`/currency, `Buchungsdatum`/posting date. I map a set of aliases.
- **`DD.MM.YYYY` dates.**
- **Opaque plant codes** (`DE01`) that mean nothing without a lookup → resolved to a
  `Facility`; unresolved codes are flagged `UNMAPPED_CODE`.
- **Mixed units for fuel** (L / Liter / LTR / GAL / m³) → normalized; gallons converted.
- **One file, two scopes**: fuel rows are Scope 1 combustion; everything else is treated as
  Scope 3 procurement spend (valued by amount + currency). This split is real and is why a
  single SAP file produces both scopes.

### What subset I handle / ignore
I handle a movements-style export with the columns above. Fuel classification keys off the
material group (`FUEL`) and material text. Procurement is spend-based (a monetary amount),
not line-item physical goods. I ignore: movement-type semantics, tax lines, multi-line
document structure, and material master enrichment.

### Sample data — why it looks like this
`sap_fuel_procurement.csv` is semicolon-delimited with German headers and one row for each
behaviour I want to prove: a clean diesel row (comma decimal), natural gas in m³, a gallons
row (unit conversion), two procurement rows (EUR and INR spend), an unknown plant code, a
negative "correction" posting, an unknown unit, and an implausible 150,000 L outlier.

### What would break in real deployment
- Real exports have dozens more columns and inconsistent column ordering between
  configurations; alias mapping would need to grow and would still miss edge cases.
- Material-group conventions differ per client — "is this row fuel?" is not universally
  answerable from a group code.
- True procurement carbon needs line-item or category-level spend factors, multi-currency
  conversion, and FX dates. I handle a single factor per currency.

---

## 2. Utility — electricity

**Ingestion mechanism chosen: portal CSV export.**

### Real-world format
A facilities team gets electricity data three ways: a CSV download from the utility's online
portal, a PDF bill, or (rarely) an API. I chose the portal CSV:
- **PDF bills**: layout differs per utility; OCR/table extraction is brittle and high-effort
  for low marginal signal in a prototype.
- **APIs**: most utilities, especially outside the US/UK, expose none.

### What I learned (and handle)
- **Billing periods do not align to calendar months** (e.g. Jan 5 – Feb 4). I store
  `period_start`/`period_end` natively and never re-bucket into months — month allocation is
  a downstream reporting decision, not an ingestion one.
- **Units vary** (kWh / MWh) → normalized to kWh.
- **Meter/site IDs** resolve to a `Facility`, whose `country` selects the grid emission
  factor (an Indian kWh ≠ a German kWh).
- **Blank consumption** happens (estimated reads, pending bills) → flagged `MISSING_QTY`,
  never assumed zero.

### Sample data — why it looks like this
`utility_electricity.csv` has a month-crossing billing period, an MWh row (conversion), an
Indian site (different grid factor), an unknown site (`UNMAPPED_CODE` → global fallback
factor), and a blank-consumption row. `utility_correction.csv` re-sends one overlapping
period from a separate "batch" to demonstrate cross-source `POSSIBLE_DUPLICATE` detection.

### What would break in real deployment
- Real portals export tariff blocks, multiple registers (day/night), demand charges, and
  reactive power — I keep only consumption.
- Meter-to-facility mapping is messy (sub-meters, shared meters, tenant splits).
- Market-based vs location-based Scope 2 accounting (RECs/PPAs) is not modelled.

---

## 3. Corporate travel — flights, hotels, ground

**Ingestion mechanism chosen: JSON export shaped like a Concur/Navan trip feed.**

### Real-world format
Concur (v3 API) and Navan do expose REST APIs, but they need OAuth, partner approval, and a
live tenant — not feasible for a prototype, and the assignment is explicit that we should
not pretend to. What those APIs return is JSON: a list of trip segments, each with a `type`.
I ingest that JSON shape directly. Swapping to a live API pull later is a transport change,
not a model change.

### What I learned (and handle)
- **Distances are often missing** — you get airport codes, not kilometres. I derive distance
  with a great-circle (haversine) calculation from a small airport-coordinate table and flag
  the row `DISTANCE_ESTIMATED` so the analyst knows the number was derived, not given.
- **Three categories, three emission bases**: flights bill per passenger-km (factor varies
  by short/long haul), hotels per room-night (factor varies by country), ground per km
  (factor varies by mode). The model carries all three through the same `quantity × factor`.
- **Unknown airport codes** → no distance, flagged `UNMAPPED_CODE`, co2e not computed.

### Sample data — why it looks like this
`travel.json` has a flight with no distance (estimated), a long-haul flight with distance
given, a flight to an unknown airport (`ZZZ`), two hotels in different countries (different
factors), taxi and rail ground legs, and a `helicopter` segment of an unknown type that
**fails** (no ActivityRecord) — proving the failed-row path.

### What would break in real deployment
- The airport table here is ~13 hand-picked codes; production needs the full OurAirports
  dataset (~75k) and IATA/ICAO disambiguation.
- Real flight factors depend on cabin class, aircraft type, radiative forcing, and
  load factors — I use a two-bucket short/long-haul approximation.
- Hotels and ground vary far more than country/mode; spend-based fallbacks are often needed.

---

## A note on the emission factors
All factor values in `seed.py` are representative of published sources (DEFRA 2024, IEA grid
intensities, generic EEIO spend factors) but are **fabricated for the prototype** and marked
as illustrative. They are not an authoritative factor set and must not be used for real
reporting.
