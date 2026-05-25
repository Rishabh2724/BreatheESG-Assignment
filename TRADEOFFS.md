# Tradeoffs

Three things I deliberately did **not** build, and why. (More minor cuts are noted inline in
DECISIONS.md; these are the three that most shape the product.)

## 1. No live source connectors (SAP RFC/OData, Concur/Navan OAuth, utility APIs)

**What I skipped:** real-time/scheduled pulls from the source systems. Everything is file or
JSON upload.

**Why:** every live connector needs credentials, partner approval, and middleware against a
system I don't have. Building a fake one would prove nothing, and the assignment explicitly
warns against pretending. The realistic v1 handoff for an ESG vendor *is* a file export.
Critically, the **data model doesn't change** when a connector is added later — a connector
just becomes another way to fill an `ImportBatch` with `RawRecord`s. So this is a transport
gap, not a modelling gap.

**Cost of skipping:** no freshness/scheduling, and someone has to export and upload manually.

## 2. No versioned emission-factor service

**What I skipped:** a factor database versioned by year, methodology, and geography, with the
ability to re-run historical calculations under the factor set that was current at the time.

**Why:** a proper factor service is a project in itself (sourcing DEFRA/EPA/IEA/ecoinvent,
modelling validity windows, methodology provenance, recomputation). For a prototype it would
swallow the time that the data model — the thing actually graded — deserves. I seeded a
small, flat, clearly-labelled-illustrative factor table and matched against it
deterministically. The model leaves room for this: `EmissionFactor` already has `valid_from`
and `source`, and co2e is recomputed from the linked factor.

**Cost of skipping:** factors are static and illustrative; not usable for real reporting,
and no "as-of-date" recalculation.

## 3. No real auth/RBAC, and no controlled re-open of locked rows

**What I skipped:** signup, password reset, org provisioning, fine-grained roles and
maker/checker separation — and the workflow to reopen a row after it's been locked for audit.

**Why:** the assignment grades multi-tenancy *in the model* and analyst UX, not an auth
system. A seeded demo org with analyst/admin users is enough to demonstrate tenant isolation
and "who did what" in the audit trail. Locking is intentionally one-way in the prototype
because a sloppy reopen path is worse than none — a real reopen must itself be an audited,
permissioned action tied to the client's audit process, which I'd want to design with the PM
rather than guess.

**Cost of skipping:** can't self-serve new orgs/users; a genuine post-sign-off correction
currently has no in-app path (would require admin/DB intervention).

---

### Honourable mentions (smaller, also deliberate)
- **Outlier detection is a static ceiling**, not a per-facility statistical baseline.
- **Duplicates are flagged, not merged** — no supersede/merge workflow.
- **No background job queue** — ingestion runs synchronously in the request. Fine for files
  this size; a large file would need Celery/RQ.
- **Billing periods aren't allocated to calendar months** — that's a reporting feature, kept
  out of the source-of-truth layer on purpose.
