# Tradeoffs

Three things I chose not to build, and why. (Smaller cuts are noted inline in DECISIONS;
these are the three that actually shape the product.)

## 1. No live source connectors

I skipped real-time or scheduled pulls from SAP (RFC/OData), Concur/Navan (OAuth), and utility
APIs. Everything is a file or JSON upload.

Every one of those connectors needs credentials, partner approval, and middleware against a
system I don't have, and a fake one would prove nothing. The honest v1 handoff for an ESG
vendor is a file export anyway. The part that matters: the data model doesn't change when a
connector is added later. A connector is just another way to fill an `ImportBatch` with
RawRecords. So this is a transport gap, not a modeling gap.

What it costs: no freshness or scheduling, and someone has to export and upload by hand.

## 2. No versioned emission-factor service

I skipped a factor database versioned by year, methodology and geography, with the ability to
re-run old calculations under the factor set that was current at the time.

A real factor service is a project on its own (sourcing DEFRA/EPA/IEA/ecoinvent, modeling
validity windows and methodology provenance, recomputation). For a prototype it would eat the
time the data model deserves, and the data model is what's graded. So I seeded a small, flat,
clearly-labelled-illustrative table and match against it deterministically. The model leaves
room for the real thing: `EmissionFactor` already has `valid_from` and `source`, and co2e is
recomputed from the linked factor.

What it costs: factors are static and illustrative, not usable for real reporting, and there's
no "as-of-date" recalculation.

## 3. No real auth/RBAC, and no reopening of locked rows

I skipped signup, password reset, org provisioning, fine-grained roles and maker/checker
separation, plus the flow to reopen a row after it's been locked for audit.

The assignment grades multi-tenancy in the model and analyst UX, not an auth system. A seeded
org with analyst/admin users is enough to show tenant isolation and "who did what." Locking is
one-way on purpose, because a sloppy reopen path is worse than none: it would let someone
quietly change audit-sealed numbers. A real reopen has to be a permissioned, audited action
tied to the client's audit process, and I'd rather design that with the PM than guess.

What it costs: can't self-serve new orgs/users, and a genuine post-sign-off correction has no
in-app path today (needs admin/DB intervention).

## Smaller ones, also on purpose
* Outlier detection is a static ceiling per unit, not a per-facility statistical baseline.
* Duplicates are flagged, not merged. No supersede flow.
* Ingestion runs synchronously in the request. Fine for files this size; a big file would want
  Celery/RQ, and the `ImportBatch` status field already anticipates that.
* Billing periods aren't allocated to calendar months. That's a reporting feature, kept out of
  the source-of-truth layer deliberately.
