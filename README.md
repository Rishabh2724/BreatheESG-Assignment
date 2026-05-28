# Breathe ESG — emissions ingestion & review prototype

Takes emissions/activity data from three kinds of source (SAP fuel & procurement, utility
electricity, corporate travel), normalizes it, and gives analysts a dashboard to review what
came in, what looks off, and what failed, then approve and lock rows for audit.

Django REST + React + Postgres.

Start with [MODEL.md](MODEL.md) — it explains the one idea the rest hangs off. The reasoning
is in [DECISIONS.md](DECISIONS.md), the things I left out in [TRADEOFFS.md](TRADEOFFS.md), and
the per-source research in [SOURCES.md](SOURCES.md). There's also a deeper pipeline writeup in
[PIPELINE.md](PIPELINE.md).

## Demo login
```
analyst / analyst123      reviews, edits, approves, locks
admin   / admin123          also gets Django /admin
```

## How it fits together

```
React SPA  --/api-->  Django REST  -->  Postgres
                          |
        pipeline: per-source parser -> normalize -> match factor -> validate
                          |
   RawRecord (verbatim, never edited)  --1:1-->  ActivityRecord (normalized, reviewable)
                                                       |
                                                  AuditEvent (append-only)
```

Backend lives in `backend/`: `ingest/models.py` is the data model, `ingest/pipeline/` is the
parsers + normalizer + factor matching + validators, `ingest/services.py` is the review/edit/
lock logic, `ingest/views.py` is the tenant-scoped API, `ingest/tests.py` has the 11 tests on
the invariants I care about.

Frontend is in `frontend/` (Vite + React): dashboard, batch review table, and a per-row drawer
that shows the raw source row next to the normalized values, with plain-English flag
explanations and the audit trail.

## Running it locally

Needs Python 3.12+, Node 18+, and a Postgres database.

Backend:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# point at your Postgres (or copy backend/.env.example to backend/.env)
export DATABASE_URL=postgres://USER:PASS@localhost:5432/DBNAME

cd backend
python manage.py migrate
python manage.py seed --fresh        # demo org, factors, facilities, 3 ingested batches
python manage.py runserver           # http://127.0.0.1:8000
```

Frontend (dev):
```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173, proxies /api to :8000
```

As a single server (the way Render runs it):
```bash
cd frontend && npm run build         # outputs to backend/web_build/
cd ../backend && python manage.py collectstatic --noinput
python manage.py runserver           # SPA + API both on http://127.0.0.1:8000
```

Tests:
```bash
cd backend && python manage.py test ingest
```

## API (everything under `/api/`, token auth)

| Method | Path | What it does |
|--------|------|--------------|
| POST | `/auth/token/` | username+password to token |
| GET | `/me/`, `/summary/` | current user; dashboard rollup |
| GET/POST | `/batches/` | list batches; POST is a multipart upload (`source_type`, `file`) that ingests |
| GET | `/records/?batch=&status=&scope=&flagged=` | filtered canonical rows |
| GET | `/records/{id}/` | one row with its raw payload and audit trail |
| PATCH | `/records/{id}/` | edit fields (recomputes co2e, writes audit; 409 if locked) |
| POST | `/records/{id}/approve\|reject\|lock/` | state changes |
| POST | `/records/bulk_action/` | `{ids, action}` |

## Deploying (Render)

[`render.yaml`](render.yaml) sets up one web service and one managed Postgres. The React app
is built locally into `backend/web_build` and committed, so the Render build is Python-only:
`pip install -> collectstatic -> migrate -> seed`. `SECRET_KEY` is generated and `DATABASE_URL`
is wired from the database, so there's nothing to set by hand.

To push a frontend change: `cd frontend && npm run build`, commit `backend/web_build`, push.
