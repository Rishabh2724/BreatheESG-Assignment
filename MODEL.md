# Data Model

The thing I kept reminding myself building this: the hard part isn't the carbon arithmetic,
it's trust. When an auditor points at a number, I have to be able to show where it came
from, what the source actually said, who touched it, and when. So the model is shaped around
that, not around "store some emissions."

## The core idea: keep raw and normalized separate

There are two tables doing the real work:

* `RawRecord` is the source line exactly as it arrived. Original headers, original units,
  whatever junk was in it, stored as JSON. I never edit this.
* `ActivityRecord` is the cleaned-up, carbon-bearing version derived from a RawRecord. This
  is the only thing an analyst edits, approves, and locks.

Each ActivityRecord has a one-to-one link back to the RawRecord it came from. That link is
the whole point. It means "which source produced this / was it edited" isn't a convention I
have to remember to maintain, it falls out of the schema:

* Which source? `raw_record.batch` has the source type, filename, who uploaded it, when.
* Was it edited? `edited_by` / `edited_at` on the canonical row, plus the AuditEvent log. The
  RawRecord still shows the original, so you can always diff.
* What changed in normalization? `original_quantity` / `original_unit` hold the verbatim
  values; `quantity` / `unit` hold the cleaned ones.

If a line can't be parsed at all, I still write the RawRecord (with a `parse_error`) and
just don't create an ActivityRecord. That's what "failed" means on the dashboard. A line
that parses but looks wrong gets an ActivityRecord with `status=flagged`. So the three
buckets the PM asked for (came in / suspicious / failed) aren't a feature I bolted on,
they're three states of the same pipeline.

## Tables

| Model | What it's for |
|-------|---------------|
| `Organization` | The tenant. Everything carries `org_id`. |
| `User` | Has an `org` and a role (analyst/admin). |
| `Facility` | What SAP plant codes and utility meters resolve to. Holds the country. |
| `EmissionFactor` | A `quantity -> kgCO2e` factor, matched by category/region/fuel/currency. |
| `ImportBatch` | One upload. Holds the source type and the ok/flagged/failed counts. |
| `RawRecord` | The untouched source line, as JSON. |
| `ActivityRecord` | The normalized, reviewable row. The editable surface. |
| `AuditEvent` | Append-only log of every change. |

## Going through the requirements one by one

### Multi-tenancy
Every table has an `org` FK and every query goes through one place, `TenantScoped.get_queryset()`,
which filters on `request.user.org`. One org can't see another's rows. There's a test for
exactly this (`TenancyTests`): a second org asking for the first org's record gets a 404, not
a leak.

I didn't do schema-per-tenant or a database per tenant on purpose. For the number of tenants
a prototype has, that's a lot of operational pain (migrations across N schemas, routing) for
no real benefit. The downside of a shared schema is that one forgotten `.filter(org=...)`
leaks data, so I funnel every query through the mixin and pin it with a test. If this were
real and big, I'd add Postgres row-level security underneath as a second guard. Said so in
TRADEOFFS.

### Scope 1 / 2 / 3
Scope comes from the category, not the source, because one source crosses scopes: a single
SAP export has fuel (Scope 1) and procurement spend (Scope 3) in the same file. The
category-to-scope mapping lives in exactly one dict (`pipeline/base.py`, `SCOPE_BY_CATEGORY`)
so no parser can quietly disagree with another. I store the scope on the row rather than
recomputing it, because an analyst can override it and I want the override in the audit log.

Categories: `stationary_combustion`, `mobile_combustion` (S1); `purchased_electricity` (S2);
`purchased_goods`, `business_travel_air` / `_hotel` / `_ground` (S3).

### Source-of-truth tracking
Covered by the raw/canonical split above. For any row: the source and ingest time are on the
batch, the original values are on the RawRecord and the `original_*` fields, and human edits
are on `edited_by`/`edited_at` plus AuditEvent rows with `action="edit"`.

### Unit normalization
The parser converts to a canonical unit and keeps both. `quantity`/`unit` are normalized
(L, m³, kWh, km, p-km, room-night, or a currency amount for spend). `original_quantity`/
`original_unit` keep what the file said. Conversions I handle: gallons to litres, MWh to kWh,
German comma decimals like `1.250,50`, that kind of thing. If a unit is unknown I do not
guess. The row gets `MISSING_UNIT`, the normalized value stays blank, and co2e isn't
computed.

One thing I was deliberate about: natural gas stays in m³ with a kgCO2e/m³ factor. Converting
gas volume into "litres" and applying a per-litre factor is just dimensionally wrong, so I
didn't.

### Emission factors and co2e
co2e is always `quantity * factor_value`. Same formula for every category, because the
parsers do the work of making `quantity` be the thing the factor multiplies (a flight's
quantity is `distance * passengers` in p-km, for example). I compute co2e at ingest so the
analyst has a number to sanity-check, but it stays provisional until the row is locked. Factor
matching is in `pipeline/factors.py` and is deterministic: fuel type and currency have to
match exactly, only region falls back to a global default.

### Audit trail and locking
`AuditEvent` is append-only. Nothing in the app ever updates or deletes one. Edits, approvals,
rejections and locks each write a row with actor, field, old, new. An approved row can be
locked, and locking is one-way: a locked row is immutable and edits get a 409. That's in
`services.py` and tested in `LockTests`. Reopening a locked row in a real system would itself
be a controlled, audited action, which I left out (see TRADEOFFS).

## Flags
`flags` is a list on each ActivityRecord. The rule I stuck to: a flag makes a judgement call
visible to a person, it never changes the data. Current flags: `MISSING_QTY`, `NEGATIVE_QTY`,
`MISSING_UNIT`, `UNMAPPED_CODE`, `NO_FACTOR`, `OUTLIER`, `POSSIBLE_DUPLICATE`,
`DISTANCE_ESTIMATED`. Any flag sets the row to `flagged`. The duplicate check (same facility +
category + overlapping period, in a different batch) is the one place I acknowledge the same
activity showing up from two systems. I flag it and let a human decide; I don't auto-merge,
because merging silently changes a reported number.

## What I'd change if this were real
* Postgres row-level security as a backstop on tenancy.
* A proper versioned factor library (by year, methodology, geography) instead of the flat
  seeded table. The `valid_from` field is already there for it.
* Real outlier detection (rolling baselines per facility) instead of static ceilings.
* A controlled reopen flow for locked rows.
