# Data Model

The hard part here isn't the carbon math, it's trust: when an auditor points at a number I
have to show where it came from, what the source said, who changed it, and when. The model is
built around that.

## Core idea: raw and normalized are separate tables

* `RawRecord` — the source line exactly as it arrived (original headers, units, junk) stored
  as JSON. Never edited.
* `ActivityRecord` — the cleaned, carbon-bearing row derived from it. The only thing an
  analyst edits, approves, locks.

One-to-one link from ActivityRecord back to RawRecord. That link is why provenance is
structural, not a convention:

* which source / when → `raw_record.batch` (source type, filename, uploader, timestamp)
* was it edited → `edited_by`/`edited_at` + the AuditEvent log; RawRecord still holds the
  original so you can diff
* what normalization changed → `original_quantity`/`original_unit` vs `quantity`/`unit`

A line that can't be parsed still gets a RawRecord with a `parse_error` and no ActivityRecord
(that's "failed"). A line that parses but looks wrong becomes an ActivityRecord with
`status=flagged`. So the dashboard's three buckets (came in / suspicious / failed) are just
pipeline states, not a bolted-on feature.

## Tables

| Model | For |
|-------|-----|
| `Organization` | tenant; everything carries `org_id` |
| `User` | has `org` + role (analyst/admin) |
| `Facility` | what SAP plant codes / utility meters resolve to; holds country |
| `EmissionFactor` | a `quantity → kgCO2e` factor, matched by category/region/fuel/currency |
| `ImportBatch` | one upload; holds source type + ok/flagged/failed counts |
| `RawRecord` | untouched source line, as JSON |
| `ActivityRecord` | normalized reviewable row; the editable surface |
| `AuditEvent` | append-only log of every change |

## Requirements, point by point

**Multi-tenancy.** `org` FK on every table; every query goes through `TenantScoped.get_queryset()`
(filters by `request.user.org`). One org can't see another's rows — pinned by `TenancyTests`
(cross-org request gets 404). Not schema-/db-per-tenant: too much ops weight for a prototype.
The risk (a forgotten `.filter(org=...)`) is contained by routing everything through the mixin;
at scale I'd add Postgres row-level security.

**Scope 1/2/3.** Derived from category, not source, because one SAP file has both Scope 1
(fuel) and Scope 3 (procurement). The category→scope map is one dict (`pipeline/base.py`,
`SCOPE_BY_CATEGORY`) so parsers can't disagree. Scope is stored (not recomputed) so an analyst
can override it, with the override audited. Categories: stationary/mobile combustion (S1),
purchased_electricity (S2), purchased_goods + business_travel_air/hotel/ground (S3).

**Source of truth.** Covered by the raw/canonical split: source + time on the batch, original
values on RawRecord and the `original_*` fields, human edits on `edited_by`/`edited_at` + the
audit log.

**Unit normalization.** Parser converts to a canonical unit and keeps both. Handles gallons→L,
MWh→kWh, German comma decimals (`1.250,50`). Unknown unit is never guessed: flagged
`MISSING_UNIT`, value left blank, no co2e. Natural gas stays in m³ with a kgCO2e/m³ factor —
converting gas volume to litres is dimensionally wrong.

**Factors + co2e.** Always `co2e = quantity × factor_value`; the parsers make `quantity` the
thing the factor multiplies (a flight's quantity is `distance × passengers`). Computed at
ingest so it's visible, but provisional until lock. Matching (`pipeline/factors.py`) is
deterministic: fuel type and currency match exactly, only region falls back to a global
default.

**Audit + lock.** `AuditEvent` is append-only (never updated/deleted); edits, approvals,
rejections, locks each write actor/field/old/new. Approved → locked is one-way; a locked row
is immutable and edits return 409 (`services.py`, tested in `LockTests`). A controlled reopen
would be its own audited action — left out (TRADEOFFS).

**Flags.** A list on each row; a flag makes a judgement call visible, never changes data.
`MISSING_QTY`, `NEGATIVE_QTY`, `MISSING_UNIT`, `UNMAPPED_CODE`, `NO_FACTOR`, `OUTLIER`,
`POSSIBLE_DUPLICATE`, `DISTANCE_ESTIMATED`. Any flag sets `flagged`. `POSSIBLE_DUPLICATE` =
same facility + category + overlapping period in a different batch; flagged for a human, never
auto-merged.

## If this were real
Postgres row-level security on tenancy; a versioned factor library (the `valid_from` field is
already there); statistical outlier baselines instead of static ceilings; a controlled reopen
flow for locked rows.
