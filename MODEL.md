# Data Model

The hard part of this problem is not carbon math. It is **trust**: when an auditor looks
at a number, we must be able to show exactly which file it came from, which row, what we
did to it, who touched it, and when. The model is built around that requirement.

## The one idea: two layers

```
RawRecord  ──(1:0..1)──▶  ActivityRecord
  the receipt                the reviewable, carbon-bearing row
  never mutated              normalized + editable
```

- **RawRecord** stores one source line exactly as it arrived — original headers, original
  units, original junk — as a JSON blob plus its line number. It is never edited.
- **ActivityRecord** is the normalized row derived from a RawRecord. It is the only thing
  an analyst edits, approves, and locks.

Every ActivityRecord has a `OneToOneField` back to its RawRecord. That single link is what
makes "source of truth" structural rather than a convention we hope everyone follows:

- **Which source produced this row?** → `raw_record.batch.source_type` + `batch.filename`.
- **Was it edited?** → `edited_by` / `edited_at` on the canonical row, plus the full
  `AuditEvent` history; the RawRecord shows what the original said.
- **What did we change?** → compare `original_quantity`/`original_unit` (verbatim from raw)
  against `quantity`/`unit` (normalized).

If a line cannot be normalized at all, we still create the RawRecord (with `parse_error`)
and create **no** ActivityRecord. That is what "failed" means on the dashboard. A line that
normalizes but looks wrong becomes an ActivityRecord with `status=flagged`. So the three
dashboard buckets — ingested / suspicious / failed — fall directly out of the model.

## Entities

| Model | Purpose |
|-------|---------|
| `Organization` | Tenant root. Every business row carries `org_id`. |
| `User` | Custom user with `org` FK and a coarse `role` (analyst/admin). |
| `Facility` | The lookup SAP plant codes / utility meters resolve to. Holds `country`. |
| `EmissionFactor` | A conversion factor `quantity → kgCO2e`, matched by category/region/fuel/currency. |
| `ImportBatch` | One ingestion event (one upload). Holds source type + ok/flagged/failed tallies. |
| `RawRecord` | Immutable receipt — one source line, verbatim, as JSON. |
| `ActivityRecord` | Normalized, reviewable, carbon-bearing row. The editable surface. |
| `AuditEvent` | Append-only log of every change (actor, field, old → new). |

## How it satisfies each required property

### Multi-tenancy
Every business table has an `org` FK. Reads and writes are scoped in one place —
`TenantScoped.get_queryset()` filters by `request.user.org` — so one org physically cannot
read or mutate another's rows. Tested in `TenancyTests` (a second org gets a 404, not a
leak).

We deliberately did **not** use schema-per-tenant or a database per tenant. For the number
of tenants a prototype models, that is operational weight with no payoff; a single shared
schema with disciplined scoping is simpler to reason about and to test. The cost (one
missed `.filter(org=…)` leaks data) is mitigated by routing every query through the mixin
and asserting isolation in tests. At real scale you would add Postgres row-level security
as a second line of defence — noted in TRADEOFFS.md.

### Scope 1 / 2 / 3 categorization
Scope is **derived from category, not from source**, because one source spans scopes:
a single SAP file produces Scope 1 (fuel combustion) *and* Scope 3 (procurement spend).
The category→scope mapping lives in exactly one place (`pipeline/base.py:SCOPE_BY_CATEGORY`)
so no parser can disagree. Scope is then **stored** on the row (not recomputed on read) so
an analyst can override it, and any override is written to the audit trail.

Categories: `stationary_combustion`, `mobile_combustion` (S1) · `purchased_electricity`
(S2) · `purchased_goods`, `business_travel_air`/`_hotel`/`_ground` (S3).

### Source-of-truth tracking (which source, when, edited?)
Covered by the two-layer split above. Concretely, every ActivityRecord answers:
- source + ingest time → `batch`
- original values → `raw_record.payload` and `original_quantity`/`original_unit`
- human edits → `edited_by`, `edited_at`, and `AuditEvent` rows with `action="edit"`

### Unit normalization
The parser converts to a canonical unit and records both: `quantity`/`unit` are normalized
(L, m³, kWh, km, p-km, room-night, or a currency amount for spend); `original_quantity`/
`original_unit` keep what the source said. Conversions handled: gallons→L, MWh→kWh,
German comma decimals (`1.250,50`), and so on. **Unknown units are never guessed** — the
row is flagged `MISSING_UNIT`, normalized value left blank, and co2e not computed.

A deliberate dimensional choice: natural gas metered in m³ stays in m³ with a kgCO2e/m³
factor. Converting gas *volume* to "litres" and applying a litre factor would be
dimensionally wrong, so we don't.

### Emission factors and CO₂e
`co2e_kg = quantity × factor_value`, uniform across every category — the parser does the
work of making `quantity` the thing the factor multiplies (e.g. a flight's quantity is
`distance × passengers` in p-km). co2e is computed **at ingest** so an analyst sees a number
to sanity-check, but it stays **provisional until the row is locked**. Factor matching is
deterministic: fuel/currency must match exactly; only region relaxes to a global fallback
(`pipeline/factors.py`).

### Audit trail + locking
`AuditEvent` is append-only — never updated, never deleted. Edits, approvals, rejections,
and locks each write one event with actor, field, old, and new value. Approved rows can be
**locked**, which is one-way: a locked row is immutable and edits are rejected with HTTP 409
(`services.transition` / `apply_edit`, tested in `LockTests`). Reopening a locked row in a
real system would itself be a controlled, audited action — out of scope here (TRADEOFFS.md).

## Validation flags (surfaced, never silently fixed)

`flags` is a list on each ActivityRecord. Flags make a judgement call visible to a human;
they never alter the data. Current flags: `MISSING_QTY`, `NEGATIVE_QTY`, `MISSING_UNIT`,
`UNMAPPED_CODE`, `NO_FACTOR`, `OUTLIER`, `POSSIBLE_DUPLICATE`, `DISTANCE_ESTIMATED`. Any flag
sets `status=flagged`. The cross-source `POSSIBLE_DUPLICATE` check (same facility + category
+ overlapping period in a different batch) is the one place we acknowledge the same activity
arriving from two systems — we flag it for a human and never auto-merge.

## What I would change at scale
- Postgres row-level security as defence-in-depth on tenancy.
- A real, versioned emission-factor service (by year, methodology, geography) instead of the
  flat seeded table.
- Statistical outlier detection per facility instead of static ceilings.
- A controlled "reopen locked row" workflow for genuine post-lock corrections.
