# Sources

For each of the three sources: the format I looked at, what's actually annoying about it, what
my sample file looks like and why, and what would break for real. Sample files are in
`backend/sample_data/`.

---

## 1. SAP — fuel & procurement

I ingest this as a flat-file CSV upload.

### What's out there
SAP can hand you data as IDoc, BAPI/RFC, or OData services. I didn't go after any of them on
purpose. They all need a live SAP system, RFC/OData credentials, and usually middleware
(PI/PO, CPI) in front. A prototype can't stand that up, and more to the point it isn't how
this data usually reaches an ESG vendor in the first place. What happens in practice is the
client's SAP team runs a report (an ABAP report, or something like MB51 for material
movements) and sends over a CSV or Excel file. That export is the realistic common case, so
that's what I parse.

### What I learned (and handle)
SAP exports configured for a German locale are genuinely unpleasant:
* Semicolon-delimited, because in German Excel the comma is the decimal separator.
* Comma decimals: `1.250,50` means 1250.50. I detect German vs US formatting by which
  separator comes last.
* German or English headers: `Werk`/plant, `Menge`/quantity, `Einheit`/unit, `Betrag`/amount,
  `Währung`/currency, `Buchungsdatum`/posting date. I keep a list of aliases.
* `DD.MM.YYYY` dates.
* Plant codes like `DE01` that mean nothing without a lookup, so they resolve to a `Facility`
  and unresolved ones get flagged `UNMAPPED_CODE`.
* Mixed fuel units (L / Liter / LTR / GAL / m³), normalized, gallons converted.
* One file, two scopes: fuel rows are Scope 1 combustion, everything else is Scope 3
  procurement spend (amount + currency). This is real and it's why a single SAP file produces
  both scopes.

### What I handle vs ignore
I handle a movements-style export with the columns above. Fuel gets classified off the
material group (`FUEL`) and the material text. Procurement is spend-based (a money amount),
not itemized physical goods. I ignore movement-type semantics, tax lines, multi-line document
structure, and material master enrichment.

### The sample file, and why
`sap_fuel_procurement.csv` is semicolon-delimited with German headers, and I gave it one row
per behaviour I wanted to prove: a clean diesel row (comma decimal), natural gas in m³, a
gallons row (conversion), two procurement rows (EUR and INR spend), an unknown plant code, a
negative correction posting, an unknown unit, and an absurd 150,000 L outlier.

### What breaks for real
* Real exports have many more columns and inconsistent ordering between configs, so alias
  mapping would have to grow and would still miss things.
* "Is this row fuel?" isn't universally answerable from a group code; conventions vary per
  client.
* Real procurement carbon needs line-item or category spend factors, multi-currency and FX
  dates. I do one factor per currency.

---

## 2. Utility — electricity

I ingest this as a portal CSV export.

### What's out there
A facilities team gets electricity data one of three ways: a CSV from the utility's online
portal, a PDF bill, or (rarely) an API. I went with the portal CSV.
* PDF bills: the layout changes per utility, and OCR/table extraction is fiddly and
  error-prone for not much gain in a prototype.
* APIs: most utilities, especially outside the US/UK, don't have one.

### What I learned (and handle)
* Billing periods don't line up with calendar months (e.g. Jan 5 to Feb 4). I store
  `period_start`/`period_end` as-is and don't re-bucket into months, because month allocation
  is a reporting choice, not an ingestion one.
* Units vary (kWh / MWh), normalized to kWh.
* Meter/site IDs resolve to a `Facility`, and its country picks the grid factor (an Indian kWh
  is not a German kWh).
* Blank consumption happens (estimated reads, pending bills). I flag `MISSING_QTY` and never
  assume zero.

### The sample files, and why
`utility_electricity.csv` has a month-straddling period, an MWh row (conversion), an Indian
site (different grid factor), an unknown site (`UNMAPPED_CODE`, falls back to the global
factor), and a blank-consumption row. `utility_correction.csv` re-sends one overlapping period
as a separate batch, which is how I demo the cross-source `POSSIBLE_DUPLICATE` check.

### What breaks for real
* Real portals export tariff blocks, multiple registers (day/night), demand charges, reactive
  power. I keep only consumption.
* Meter-to-facility mapping gets messy (sub-meters, shared meters, tenant splits).
* Market-based vs location-based Scope 2 (RECs/PPAs) isn't modeled.

---

## 3. Corporate travel — flights, hotels, ground

I ingest this as a JSON export shaped like a Concur/Navan trip feed.

### What's out there
Concur (v3 API) and Navan do have REST APIs, but they need OAuth, partner approval and a live
tenant, which isn't realistic for a prototype (and the brief says not to fake it). What those
APIs return is JSON: a list of trip segments, each with a `type`. So I ingest that JSON shape
directly. Swapping to a live pull later is a transport change, not a model change.

### What I learned (and handle)
* Distances are often missing. You get airport codes, not kilometres. So I compute distance
  with a great-circle (haversine) calc from a small airport coordinate table and flag the row
  `DISTANCE_ESTIMATED` so the analyst knows the number was derived, not given.
* Three categories, three emission bases: flights per passenger-km (factor differs short vs
  long haul), hotels per room-night (by country), ground per km (by mode). All three run
  through the same `quantity * factor`.
* Unknown airport codes: no distance, flagged `UNMAPPED_CODE`, co2e not computed.

### The sample file, and why
`travel.json` has a flight with no distance (estimated), a long-haul flight with distance
given, a flight to an unknown airport (`ZZZ`), two hotels in different countries (different
factors), a taxi and a rail leg, and a `helicopter` segment of an unknown type that fails (no
ActivityRecord), to prove the failed-row path.

### What breaks for real
* My airport table is ~13 hand-picked codes; production needs the full OurAirports dataset
  (~75k) and IATA/ICAO disambiguation.
* Real flight factors depend on cabin class, aircraft type, radiative forcing, load factors. I
  use a two-bucket short/long-haul approximation.
* I model ground per vehicle-km, which is right for taxis but an approximation for rail (rail
  is really per passenger-km).

---

## On the emission factors
All the factor values in `seed.py` are in the right ballpark for published sources (DEFRA
2024, IEA grid intensities, generic EEIO spend factors) but they're hand-entered and labelled
illustrative. They are not an authoritative factor set and shouldn't be used for real
reporting. The point was to get the mechanism right, not to ship a factor library.
