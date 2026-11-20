# Deploying MediCore AI to production

## Architecture

```
            Internet (HTTPS)
                   │
        TLS terminator (Caddy / Traefik / cloud load balancer)
                   │  http://web:8080
        ┌──────────▼──────────┐
        │ web: nginx + SPA    │  CSP, gzip, immutable asset caching, SPA routing
        │  /api/* ─────────┐  │  same-origin proxy (no CORS)
        └──────────────────┼──┘
                           ▼
        ┌─────────────────────┐   ┌────────────┐   ┌────────────┐
        │ api: FastAPI         │──▶│ PostgreSQL │   │ Redis      │
        │ uvicorn × N workers  │   │ (volume)   │   │ rate limits│
        │ models baked in image│──────────────────▶└────────────┘
        └─────────────────────┘
          │ outbound: Gemini API · OpenStreetMap (Overpass → Nominatim fallback)
        migrate: one-shot `alembic upgrade head` before the API starts
```

Only `web` is published. The API, PostgreSQL and Redis run on an internal Docker network.

## 1. Prerequisites

* Docker 24+ with Compose v2. The host needs ≥ 4 GB RAM: each API worker loads PyTorch, the embedding model and the risk model, roughly 0.6–0.9 GB per worker.
* Model artifacts in `models/`, which are produced by the offline pipeline (see README §11). They are baked into the API image, so build after running the pipeline. In CI, run the pipeline or fetch the artifacts from storage before `docker build`.
* A Gemini API key (<https://aistudio.google.com/app/apikey>) for AI-written answers. Without one, the assistant answers with verbatim, cited quotes from its sources.

## 2. Configure

```bash
cp .env.production.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # → JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(24))"   # → POSTGRES_PASSWORD
```

Set at least:

| Variable | Notes |
|---|---|
| `JWT_SECRET_KEY` | ≥ 32 random characters. Changing it signs everyone out |
| `POSTGRES_PASSWORD` | Database password |
| `GEMINI_API_KEY` | AI answers |
| `FRONTEND_URL`, `CORS_ORIGINS` | Your public URL, e.g. `https://medicore.example.org` |
| `ALLOWED_HOSTS` | Your hostname(s), e.g. `medicore.example.org` |
| `SMTP_*` | Needed for password-reset emails. Without SMTP, production does not send reset links |
| `OSM_USER_AGENT` | Identify your deployment with a real URL or email. OpenStreetMap rejects placeholders |
| `OPERATOR_NAME`, `SUPPORT_EMAIL` | Shown on the Help, Privacy and Terms pages. Empty means those pages name no one. Set them before launch |

The API **refuses to start in production** if:
- the JWT secret is weak
- the database is SQLite
- CORS is `*`
- Redis is missing while there are multiple workers
- the OSM user agent is a placeholder

## 3. Build and run

```bash
docker compose up -d --build
docker compose ps                         # migrate exits 0; api, web, db, redis are healthy
curl -s localhost:8080/api/ready          # {"status":"ready","checks":{...}}
python e2e/smoke.py --base-url http://localhost:8080 --channel chrome   # full browser smoke test
```

## 4. HTTPS

Put a TLS-terminating proxy in front of `web:8080`. For example, Caddy:

```
medicore.example.org {
    reverse_proxy localhost:8080
}
```

Uvicorn trusts `X-Forwarded-*` headers from the proxy chain, so rate limits and logs see real client IPs.
In production the API sends HSTS.

## 5. Operations

| Task | How |
|---|---|
| Health | `GET /api/health` (liveness), `GET /api/ready` (DB + model; 503 if not ready) |
| Logs | `docker compose logs -f api`. JSON lines with `request_id`. Every response carries `X-Request-ID` |
| Backups | `docker compose exec db pg_dump -U medicore medicore \| gzip > backup-$(date +%F).sql.gz`. Schedule daily and keep copies off-host |
| Restore | `gunzip -c backup.sql.gz \| docker compose exec -T db psql -U medicore medicore` |
| Upgrade | `git pull && docker compose up -d --build`. The `migrate` step applies new Alembic migrations before the API starts |
| Retrain / rebuild KB | Run the offline pipeline, then `docker compose up -d --build api` (artifacts are versioned in `models/`) |
| Scale | Raise `WEB_CONCURRENCY` (one worker per ~0.8 GB RAM), or run more `api` replicas. Redis keeps rate limits consistent |
| Rotate JWT secret | Change `JWT_SECRET_KEY` and restart. All sessions end |

## 6. Split hosting (Render API + Vercel SPA)

1. **API → Render** (Docker): use `backend/Dockerfile` with the build context at the repo root.
   - Add a managed PostgreSQL and Redis, and set the env vars above.
   - Set `CORS_ORIGINS=https://<your-vercel-app>`.
   - Add a pre-deploy command: `alembic upgrade head`.
2. **SPA → Vercel**: root `frontend/`, `VITE_API_BASE_URL=https://<your-api-host>`.
   `vercel.json` provides SPA rewrites. If you also front the SPA with the provided nginx, add the API origin
   to the CSP via `CSP_CONNECT_EXTRA=" https://<your-api-host>"`.

## 7. Security checklist

- [x] bcrypt password hashing, with password rules enforced on the client and server
- [x] JWT sessions bound to the password: changing or resetting it revokes every other session
- [x] Single-use, 15-minute password-reset links, with no account enumeration
- [x] Per-user authorization on every record, with tests for cross-user access
- [x] Rate limits on auth, chat, uploads, predictions, locator and export, backed by Redis
- [x] Uploads checked by magic bytes, extension and size, with page and pixel limits. Files are processed in memory and never stored
- [x] Strict CSP, `X-Frame-Options: DENY`, nosniff, a referrer policy and HSTS. API responses are `no-store`
- [x] Errors return a uniform envelope with no stack traces. Request IDs are used for tracing
- [x] Non-root containers. Only the web port is exposed. Secrets come from the environment only
- [x] Data export, per-category deletion, account deletion and automatic retention
- [ ] Your responsibility: TLS, backups, SMTP, monitoring and alerting
- [ ] **Legal review.** The Privacy policy and Terms pages describe what the software does, in plain words. They are not legal advice. Have a qualified professional review and adapt them for your country (health-data rules such as HIPAA or GDPR may apply) before you handle real people's information

MediCore AI is an educational tool. It is **not** a medical device and has not been clinically validated.
