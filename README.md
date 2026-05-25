# Breathe ESG — emissions ingestion & review prototype

Ingests emissions/activity data from three source types (SAP fuel & procurement, utility
electricity, corporate travel), normalizes it, and gives analysts a dashboard to review
what came in, what's suspicious, and what failed — then approve and **lock** rows for audit.

Django REST + React + Postgres.

> **Start with [MODEL.md](MODEL.md).** It explains the one idea the whole thing rests on.
> Design rationale is in [DECISIONS.md](DECISIONS.md), deliberate cuts in
> [TRADEOFFS.md](TRADEOFFS.md), per-source research in [SOURCES.md](SOURCES.md).

## Demo login
```
analyst / analyst123      (reviews, edits, approves, locks)
admin   / admin123         (also Django /admin)
```

## Architecture

```
React SPA  ──/api──▶  Django REST  ──▶  Postgres
                          │
        ingestion pipeline (per-source parser → normalize → factor → validate)
                          │
   RawRecord (verbatim, immutable)  ──1:0..1──▶  ActivityRecord (normalized, reviewable)
                                                       │
                                                  AuditEvent (append-only)
```

- **Backend** `backend/` — `ingest/models.py` (data model), `ingest/pipeline/` (parsers +
  normalizer + factor matching + validators), `ingest/services.py` (review/edit/lock logic),
  `ingest/views.py` (tenant-scoped API), `ingest/tests.py` (11 tests on the invariants).
- **Frontend** `frontend/` — Vite + React. Dashboard, batch review table, per-row drawer
  showing **raw vs normalized** side by side, plain-English flag explanations, audit trail.

## Run locally

Requires Python 3.12+, Node 18+, and a Postgres database.

### Backend
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

### Frontend (dev)
```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api to :8000)
```

### Run as a single server (prod shape)
```bash
cd frontend && npm run build         # outputs to backend/web_build/
cd ../backend && python manage.py collectstatic --noinput
python manage.py runserver           # SPA + API both served at http://127.0.0.1:8000
```

### Tests
```bash
cd backend && python manage.py test ingest
```

## API (all under `/api/`, token-authenticated)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/token/` | username+password → token |
| GET | `/me/`, `/summary/` | current user; dashboard rollup |
| GET/POST | `/batches/` | list batches; POST = multipart upload (`source_type`, `file`) → ingests |
| GET | `/records/?batch=&status=&scope=&flagged=` | filtered canonical rows |
| GET | `/records/{id}/` | detail incl. raw payload + audit trail |
| PATCH | `/records/{id}/` | edit fields (recomputes co2e, writes audit; 409 if locked) |
| POST | `/records/{id}/approve\|reject\|lock/` | state transitions |
| POST | `/records/bulk_action/` | `{ids, action}` |

## Deploy (Render)

[`render.yaml`](render.yaml) provisions one web service + one managed Postgres. The React
app is built locally into `backend/web_build` and committed, so the Render build is
Python-only: `pip install → collectstatic → migrate → seed`. Set nothing by hand —
`SECRET_KEY` is generated and `DATABASE_URL` is wired from the database.

To redeploy after a frontend change: `cd frontend && npm run build`, commit `backend/web_build`,
push.
