# MediCore AI — Technical Architecture

> Educational and research platform. MediCore AI does **not** diagnose, prescribe, or replace
> qualified healthcare professionals. Model outputs are statistical estimates from a public survey
> dataset and are **not clinically validated**.

## 1. System overview

```
                        ┌──────────────────────────────────────────────┐
                        │            React + TS SPA (Vite)              │
                        │  Tailwind · shadcn/ui · Recharts · Leaflet    │
                        │  React Router · Axios · RHF + Zod             │
                        └───────────────┬──────────────────────────────┘
                                        │ HTTPS / JSON  (JWT Bearer)
                        ┌───────────────▼──────────────────────────────┐
                        │              FastAPI (Uvicorn)                │
                        │  api/ routers → services/ → repositories      │
                        │  CORS allow-list · rate limiting · logging    │
                        │  centralized error handler · upload limits    │
                        └─┬──────────┬───────────┬───────────┬─────────┘
                          │          │           │           │
              ┌───────────▼─┐  ┌─────▼─────┐ ┌───▼──────┐ ┌──▼──────────────┐
              │ PostgreSQL  │  │ ML module │ │ RAG      │ │ External APIs   │
              │ SQLAlchemy  │  │ joblib    │ │ pipeline │ │ Gemini (LLM)    │
              │ Alembic     │  │ pipelines │ │ FAISS    │ │ OSM Overpass /  │
              │             │  │ SHAP      │ │ ST embed │ │ Nominatim (map) │
              └─────────────┘  └─────▲─────┘ └───▲──────┘ └─────────────────┘
                                     │           │
                         offline     │           │ offline
              ┌──────────────────────┴─┐   ┌─────┴──────────────────────┐
              │ src/ training pipeline │   │ src/ RAG ingestion          │
              │ data/raw → processed   │   │ CDC / WHO / PubMed → chunks │
              │ → models/*.joblib      │   │ → embeddings → FAISS index  │
              └────────────────────────┘   └─────────────────────────────┘
```

**Separation of concerns**

* **Offline pipelines** (`src/`) — reproducible scripts that ingest data, train/evaluate models and
  build the vector index. They write versioned artifacts to `models/` and `data/processed/`.
  Raw data in `data/raw/` is never modified.
* **Online API** (`backend/app/`) — loads artifacts read-only at startup; never trains at request time.
* **Frontend** (`frontend/`) — consumes only the REST API; no business logic duplicated client-side.

## 2. Key technical decisions

| Concern | Decision | Rationale |
|---|---|---|
| Prediction task | Diabetes / prediabetes risk (binary) | Well-defined, public, documented target |
| Dataset | UCI *CDC Diabetes Health Indicators* (id 891, DOI 10.24432/C53919), derived from CDC BRFSS 2015 | Public, provenance documented, 253,680 survey responses, 21 features |
| Passwords | `bcrypt` (cost 12) | Industry standard, salted |
| Tokens | JWT (HS256, PyJWT), short-lived access token | Stateless auth |
| DB | PostgreSQL 16 (Docker); SQLite allowed for local dev/tests via `DATABASE_URL` | Daemon-less dev and fast tests; same ORM models |
| Migrations | Alembic | Versioned schema |
| Rate limiting | `slowapi` on auth, chat, upload, predict | Abuse / cost protection |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-d) | Small, CPU friendly, well benchmarked |
| Vector store | FAISS `IndexFlatIP` on L2-normalised vectors (cosine) | Exact search; corpus is small |
| LLM | Google Gemini via `google-genai` SDK; LangChain text splitters for chunking | Required by spec; key from env only |
| No LLM key | Chat endpoint returns retrieved evidence + explicit "generation unavailable" notice | Never fakes generated answers |
| PDF text | PyMuPDF | Fast, accurate text layer extraction |
| OCR | Tesseract via `pytesseract` (installed in backend Docker image) | Scanned reports |
| Maps | OpenStreetMap Overpass + Nominatim, Leaflet on frontend | Real provider data, no paid key; Google Maps documented as optional alternative |
| Explainability | SHAP (`TreeExplainer` for tree models, `LinearExplainer` / permutation otherwise) | Global + local explanations |

## 3. Development roadmap

Each phase ends with: tests run, results reported, errors fixed before continuing.

| # | Module | Deliverables | Status |
|---|---|---|---|
| 0 | Architecture & scaffolding | This doc, folder structure, git, `.env.example`, `.gitignore` | ✅ |
| 1 | Backend core | Config, DB session, ORM models, Alembic, auth (register/login/me), error handling, CORS, rate limits, tests | ✅ |
| 2 | Data engineering + ML | Ingestion w/ checksum, validation, EDA report, preprocessing pipelines, feature engineering, 7 models, Stratified CV, tuning, evaluation, threshold analysis, joblib artifacts, model card | ✅ |
| 3 | ML serving + XAI | `/api/ml/*` predict / explain / models / performance / feature-importance / clusters, SHAP global + local, prediction history | ✅ |
| 4 | Segmentation | K-Means, elbow + silhouette, PCA projection, cluster statistical profiles | ✅ |
| 5 | Frontend foundation | Vite/TS/Tailwind/shadcn design system, landing, auth pages, protected layout, dashboard, analytics, explainability | ✅ |
| 6 | RAG ingestion + retrieval | Corpus fetchers (CDC/WHO/PubMed), cleaning, dedup, chunking, embeddings, FAISS, evidence-aware ranking, adaptive retrieval | ✅ |
| 7 | Generation + verification | Gemini answer generation with citations, claim-support verification, chat API + UI | ✅ code + tests · ⚠️ live Gemini output not yet exercised (no API key) |
| 8 | RAG evaluation | Benchmark set, P@K / R@K / MRR, faithfulness, citation correctness; basic vs reranked vs adaptive dashboard | ✅ retrieval measured · ⚠️ generation metrics pending API key |
| 9 | Report analyzer | Upload, PyMuPDF + OCR, lab-value parser preserving units/ranges, flags, plain-language summaries, PDF export | ✅ (OCR path needs Tesseract; in Docker image) |
| 10 | Locator, reminders, settings | OSM search + map, reminder CRUD + history, profile, password change, data export/delete | ✅ |
| 11 | Hardening & deployment | Docker images, compose, Render/Vercel guides, CI, README screenshots | ✅ production stack (nginx · API · PostgreSQL · Redis · migrations), hardening, e2e smoke test, docs/DEPLOYMENT.md |

## 4. Folder structure

```
medicore-ai/
├── frontend/                     React SPA
│   └── src/{components,pages,layouts,hooks,services,context,types,utils}
├── backend/
│   ├── app/
│   │   ├── api/                  FastAPI routers (one per domain)
│   │   ├── core/                 config, security, logging, rate limiting, errors
│   │   ├── database/             engine, session, Base
│   │   ├── models/               SQLAlchemy ORM entities
│   │   ├── schemas/              Pydantic request/response models
│   │   ├── services/             business logic
│   │   ├── ml/                   model registry, inference, SHAP explainer
│   │   ├── rag/                  retriever, ranker, generator, verifier
│   │   ├── utils/
│   │   └── main.py
│   ├── alembic/                  migrations
│   ├── tests/
│   └── requirements.txt
├── src/                          offline data & ML pipelines (python -m src.<module>)
│   ├── ingestion/  preprocessing/  feature_engineering/
│   ├── training/   evaluation/     inference/
│   └── rag_ingestion/
├── data/{raw,processed,external}
├── models/                       versioned joblib artifacts + metrics JSON
├── notebooks/                    01–04 exploratory notebooks
├── docs/
├── docker-compose.yml
├── .env.example
└── README.md
```

## 5. Database schema (PostgreSQL)

All tables have `id` (integer PK), `created_at` (timestamptz, default now). Mutable tables also
have `updated_at`. Every user-owned table has `user_id → users.id ON DELETE CASCADE` and an index
on `user_id`; every query filters by the authenticated user's id (row-level ownership).

| Table | Columns (besides id / timestamps) | Notes |
|---|---|---|
| `users` | `email` UNIQUE, `hashed_password`, `is_active`, `last_login_at` | email lower-cased; bcrypt hash only |
| `user_profiles` | `user_id` UNIQUE FK, `full_name`, `notify_email` bool, `notify_reminders` bool, `data_retention_days` int NULL | 1:1 with users. No DOB / medical history stored |
| `conversations` | `user_id` FK, `title` | |
| `chat_messages` | `conversation_id` FK (cascade), `role` (user/assistant), `content`, `sources` JSON, `verification` JSON, `retrieval_strategy` | index (conversation_id, created_at) |
| `medical_reports` | `user_id` FK, `original_filename`, `mime_type`, `size_bytes`, `sha256`, `extraction_method` (text/ocr), `status`, `summary` | file bytes are not retained after extraction by default |
| `extracted_lab_results` | `report_id` FK (cascade), `parameter`, `value_text`, `value_numeric` NULL, `unit`, `ref_low` NULL, `ref_high` NULL, `ref_text`, `flag` (low/high/normal/unknown) | ranges copied from the report, never assumed |
| `model_versions` | `name`, `version` UNIQUE(name,version), `algorithm`, `artifact_path`, `metrics` JSON, `is_active` | registry of trained models |
| `predictions` | `user_id` FK, `model_version_id` FK, `inputs` JSON, `probability`, `predicted_class`, `risk_band`, `threshold` | inputs are survey-style attributes only |
| `reminders` | `user_id` FK, `medication_name`, `dosage_note` (user-entered, free text), `frequency`, `times` JSON, `start_date`, `end_date` NULL, `is_active` | no dosage recommendation logic |
| `reminder_events` | `reminder_id` FK (cascade), `scheduled_for`, `status` (taken/skipped/missed), `logged_at` | reminder history |
| `activity_logs` | `user_id` FK, `action`, `entity_type`, `entity_id`, `metadata` JSON | index (user_id, created_at) |

Entity relationships:

```
users 1─1 user_profiles
users 1─* conversations 1─* chat_messages
users 1─* medical_reports 1─* extracted_lab_results
users 1─* predictions *─1 model_versions
users 1─* reminders 1─* reminder_events
users 1─* activity_logs
```

## 6. Frontend page structure

| Route | Access | Page | Main components | API |
|---|---|---|---|---|
| `/` | public | Landing | Navbar, Hero, Features, HowItWorks, TechStack, About, Footer | — |
| `/login` `/register` `/forgot-password` | public | Auth | AuthCard, RHF + Zod forms | `/api/auth/*` |
| `/dashboard` | protected | Dashboard | StatCards, RiskDistribution, SegmentChart, ModelStats, RecentActivity, QuickLinks | `/api/dashboard/*` |
| `/assistant` | protected | AI Assistant | ConversationList, ChatThread, Markdown, SourceCard, SuggestedQuestions | `/api/chat*` |
| `/reports` | protected | Report Analyzer | Dropzone, LabTable, FlagBadge, ReportHistory | `/api/reports*` |
| `/analytics` | protected | Predictive Analytics | PredictionForm, ResultCard, ModelComparison, ROC/PR, ConfusionMatrix, Segments, History | `/api/ml/*` |
| `/explainability` | protected | XAI | GlobalImportance, BeeswarmSummary, LocalWaterfall | `/api/ml/explain`, `/api/ml/feature-importance` |
| `/locator` | protected | Locator | SearchBar, CategoryTabs, LeafletMap, PlaceList | `/api/locations` |
| `/reminders` | protected | Reminders | ReminderForm, ReminderList, HistoryTable | `/api/reminders*` |
| `/settings` | protected | Settings | Profile, Password, Notifications, Privacy (export/delete) | `/api/users/*` |

Layout: `PublicLayout` (top nav) and `AppLayout` (collapsible sidebar + top bar with persistent
"Not medical advice · In an emergency call your local emergency number" banner).
