# Decisions

The ambiguities I hit, what I picked, and why. PM questions at the end.

## The ones that actually shaped the build

**Two tables, raw + canonical.** A single editable table can't tell you what the source said
before someone changed it. Splitting `RawRecord` (verbatim, never edited) from
`ActivityRecord` (normalized, reviewable) makes provenance and "was this edited" part of the
schema. Everything else leans on this. (MODEL)

**Scope from category, not source.** A SAP file has both Scope 1 (fuel) and Scope 3
(procurement) rows, so source can't decide scope. Category does, via one mapping. Scope is
stored and overridable, overrides audited.

**Flags surface problems, they don't fix them.** Unknown unit, missing quantity, unmapped
code, outlier: flagged and left for a person. The system never invents a value. For audit data
that's the only honest default.

**co2e at ingest, provisional until lock.** Computed immediately so the analyst has a number
to check, but not final until the row is locked, and locking is one-way.

## Ingestion mechanism per source
* SAP → CSV upload. IDoc/BAPI/OData need a live SAP + middleware; the real handoff to an ESG
  vendor is a report export anyway.
* Utility → portal CSV. PDF bills are brittle, utility APIs barely exist.
* Travel → JSON like a Concur/Navan trip feed. Their APIs return JSON; ingesting the export
  shape is the same minus the OAuth.

A live connector is a transport swap later, not a model change. (why per source: SOURCES)

## What I handled vs ignored
Per source in SOURCES. Ignored on purpose: SAP movement-type semantics, tax lines, material
master; utility tariff/register/demand detail and market-based Scope 2; travel cabin class,
aircraft type, radiative forcing.

## Tenancy
Shared schema, `org_id` everywhere, scoping in one mixin, isolation pinned by a test. Not
schema-/db-per-tenant — too much ops weight for a prototype. Row-level security is the next
step at scale.

## Procurement as spend-based Scope 3
Procurement rows are valued by money (amount + currency) against an EEIO-style factor (kgCO2e
per currency unit), not a physical quantity. That's how spend-based Scope 3 works early, when
you have the spend but not a clean activity figure. One factor per currency, no FX.

## Duplicates: flag, don't merge
Same facility + category + overlapping period across batches gets `POSSIBLE_DUPLICATE`.
Auto-merging quietly changes a reported number, and which figure is authoritative is a human
call.

## Two correctness calls
* Natural gas stays in m³ with a kgCO2e/m³ factor. Converting gas volume to litres is
  dimensionally wrong. Liquid fuels stay in litres (gallons converted).
* Utility billing periods are kept as-is, not split into calendar months. Month allocation is
  a reporting decision; doing it at ingest would bake an assumption into the source of truth.

## What I'd ask the PM
1. Which exact SAP export? The column mapping depends entirely on the client's report; I built
   for a movements-style export and would want one real file.
2. Spend-based or activity-based procurement? Changes the factor model and whether I need FX.
3. Market-based or location-based Scope 2? Decides whether I model RECs/PPAs.
4. Policy for reopening a locked row? Restatements happen; the flow depends on their audit
   process.
5. When the same activity comes from two systems, flag only or an explicit merge/supersede?
