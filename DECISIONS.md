# Decisions

The ambiguities I hit, what I picked, and why. Where I'd have asked the PM instead of
guessing, I've said so at the bottom.

## Architecture

**Two tables, raw + canonical, instead of one editable table.** A single mutable table can't
tell you what the source said before someone edited it. Splitting raw from canonical makes
provenance and "was this edited" part of the schema. This is the decision everything else
leans on. Details in MODEL.

**Scope from category, not source.** A SAP file legitimately has both Scope 1 and Scope 3
rows in it, so source type can't decide scope. Category does, through one mapping. Scope is
stored and can be overridden, and overrides are audited.

**co2e at ingest, provisional until lock.** You can't sanity-check a number you can't see, so
I compute it immediately. But it isn't final until the row is locked, and locking is one-way.

**Flags surface problems, they don't fix them.** Unknown unit, missing quantity, unmapped
code, outlier: all flagged and left for a person. The system never invents a value. For audit
data that's the only honest default.

## How I ingest each source

* SAP: CSV upload. IDoc/BAPI/OData need a live SAP plus middleware, and the real handoff to an
  ESG vendor is a report export anyway. (SOURCES §1)
* Utility: portal CSV. PDF bills are brittle to parse, utility APIs barely exist. (SOURCES §2)
* Travel: JSON shaped like a Concur/Navan trip feed. Their APIs return JSON; ingesting the
  export shape is the same thing minus the OAuth. (SOURCES §3)

## What I handled vs ignored per source
Spelled out in SOURCES. Short version of what I ignored on purpose: SAP movement-type
semantics, tax lines, material master; utility tariff/register/demand detail and market-based
Scope 2; travel cabin class, aircraft type, radiative forcing.

## Tenancy
Shared schema, `org_id` everywhere, scoping in one mixin, isolation pinned by a test. Not
schema- or db-per-tenant, that's operational weight a prototype doesn't need. Row-level
security would be the next step at scale. (MODEL)

## Auth
Token auth and a seeded demo org with an analyst and an admin. That's enough to show
multi-tenancy and "who did what" in the audit log without building signup, password reset and
RBAC, none of which is graded and all of which eats a day.

## Procurement as spend-based Scope 3
SAP procurement rows get valued by money (amount + currency) against an EEIO-style factor
(kgCO2e per currency unit), not by a physical quantity. That's how spend-based Scope 3
actually works early on, when you have the spend figure but not a clean activity quantity. One
currency per factor, no FX conversion.

## Facility as a real table, not a dict
Plant codes and meter IDs resolve to a `Facility` row that carries the country. This is the
"plant codes mean nothing without a lookup" point made concrete, and the country is what
drives the electricity grid factor. A dict in code couldn't model per-region factors cleanly.

## Duplicates: flag, don't merge
Same facility + category + overlapping period across different batches gets
`POSSIBLE_DUPLICATE`. Auto-merging would quietly change a reported number, and which figure is
authoritative is genuinely a human (or client) call.

## Billing periods kept as-is
Utility periods that straddle month boundaries are stored exactly as they came. Splitting
consumption across calendar months is a reporting decision; doing it at ingest would bake an
assumption into the source-of-truth layer.

## Natural gas in m³
Gas is metered by volume in m³ and gets a kgCO2e/m³ factor. I don't convert it to litres,
that's dimensionally meaningless. Liquid fuels stay in litres (gallons converted).
