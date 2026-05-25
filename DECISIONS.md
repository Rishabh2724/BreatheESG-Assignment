# Decisions

Every ambiguity I resolved, what I chose, why, and — where it matters — what I'd ask the PM.

## Architecture

**Two-layer model (raw + canonical) instead of one editable table.**
A single mutable table can't answer "what did the source actually say before someone edited
it." The raw/canonical split makes provenance and "was it edited" structural. This is the
core decision the whole design rests on. → MODEL.md.

**Scope derived from category, not source.**
Because one SAP file legitimately produces both Scope 1 and Scope 3, source can't determine
scope. Category does, via one mapping table. Scope is stored (overridable) and overrides are
audited.

**co2e computed at ingest, provisional until lock.**
An analyst can't sanity-check a number they can't see, so we compute immediately. But it
isn't "real" until the row is locked. Locking is one-way.

**Flags surface problems; they never fix data.**
Unknown unit, missing quantity, unmapped code, outlier — all flagged and left for a human.
The system never guesses a value. This is the honest default for audit data.

## Ingestion mechanisms (one per source, justified)

- **SAP → CSV upload.** IDoc/BAPI/OData need a live SAP + middleware; the realistic handoff
  is a report export. → SOURCES.md §1.
- **Utility → portal CSV.** PDF parsing is brittle; utility APIs are rare. → SOURCES.md §2.
- **Travel → JSON (Concur/Navan-shaped).** Their APIs return JSON but need OAuth/partner
  access; ingesting the export shape is equivalent in model terms. → SOURCES.md §3.

## Subset of each source handled / ignored
Stated per-source in SOURCES.md. Summary of what I ignored on purpose: SAP movement-type
semantics, tax lines, material master; utility tariff/register/demand detail and
market-based Scope 2; travel cabin class, aircraft type, radiative forcing.

## Tenancy
Single shared schema with `org_id` on every row and query scoping in one mixin. Not
schema/db-per-tenant — that's operational weight a prototype doesn't need. Isolation is
asserted in tests. At scale I'd add Postgres row-level security. → MODEL.md.

## Auth
Token auth + a seeded demo org with `analyst` and `admin` users. Enough to demonstrate
multi-tenancy and "who did this" in the audit trail without building signup, password reset,
and RBAC — none of which is graded and all of which eats time. → TRADEOFFS.md.

## Procurement as spend-based Scope 3
SAP "procurement" rows are valued by monetary amount + currency against an EEIO-style factor
(kgCO2e per currency unit), not by physical quantity. This is how spend-based Scope 3 is
actually done early in a company's reporting maturity. Single currency per factor; no FX
conversion.

## Facility as a real entity (not a code dict)
Plant codes and meter IDs resolve to a `Facility` row carrying `country`. This directly
answers the "plant codes mean nothing without a lookup" point and lets the country drive the
electricity grid factor. A flat dict in code couldn't model region-specific factors cleanly.

## Cross-source duplicates: detect and flag, never auto-resolve
Same facility + category + overlapping period across different batches → `POSSIBLE_DUPLICATE`
for an analyst. Auto-merging would silently change reported numbers; that's a human call.

## Billing periods kept native
Utility periods that cross month boundaries are stored as-is. Allocating consumption across
calendar months is a reporting concern, not an ingestion one, and doing it at ingest would
bake an assumption into the source-of-truth layer.

## Natural gas stays in m³
Gas is metered by volume in m³ with a kgCO2e/m³ factor. I do not convert it to "litres" —
that would be dimensionally wrong. Liquid fuels stay in litres (gallons converted).

## Deployment shape
React is built locally into `backend/web_build` and committed; Django serves the SPA shell
and WhiteNoise serves the hashed assets. This keeps the Render runtime Python-only (no Node
build step) and the app single-origin (no CORS in prod). Trade-off: the frontend must be
rebuilt and committed before deploy. Acceptable for a prototype; documented.

## What I'd ask the PM
1. **Which SAP export, exactly?** The right column mapping depends entirely on the client's
   specific report/transaction. I built for a movements-style export; I'd want one real file.
2. **Spend-based or activity-based procurement?** Changes the factor model and whether we
   need FX rates and category-level factors.
3. **Market-based or location-based Scope 2?** Determines whether we must model RECs/PPAs.
4. **What's the re-open policy for locked rows?** Auditors sometimes require corrections
   after sign-off; the controlled workflow depends on the client's audit process.
5. **Who is the reviewer, and do they need maker/checker separation?** Drives how much RBAC
   is actually required.
6. **De-duplication policy** when the same activity legitimately comes from two systems —
   flag only, or an explicit merge/supersede workflow?
