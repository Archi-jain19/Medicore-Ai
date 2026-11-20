"""MediCore AI FastAPI application entrypoint."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import auth, chat, dashboard, locations, ml, reminders, reports, users
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import limiter

_settings = get_settings()
configure_logging(_settings.log_level, _settings.log_format)
logger = logging.getLogger("medicore")

APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
DISCLAIMER = (
    "MediCore AI is an educational and research tool. It does not provide diagnoses or prescriptions "
    "and is not a substitute for a qualified healthcare professional. In an emergency, contact your "
    "local emergency services."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logger.info("Starting %s v%s (env=%s, docs=%s, llm=%s)", s.app_name, APP_VERSION, s.app_env, s.docs_enabled,
                "configured" if s.gemini_api_key else "not configured")
    if s.app_env != "test":
        from app.core.errors import AppError
        from app.ml.registry import get_registry

        try:  # warm the model so the first prediction is not slow; API still starts if artifacts are missing
            get_registry().risk_model()
        except AppError as exc:
            logger.warning("Model not loaded at startup: %s", exc.message)
        from app.rag.retriever import get_retriever

        retriever = get_retriever()
        if retriever is None:
            logger.warning("RAG knowledge base not built; the assistant will report this to users")
        else:
            retriever.embed(["warm-up"])  # load the embedding model before the first question
    yield


def _rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        {"error": {"code": "rate_limited", "message": "Too many requests. Please wait a moment and try again."}},
        status_code=429, headers={"Retry-After": "60"},
    )


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version=APP_VERSION,
        description=DISCLAIMER,
        lifespan=lifespan,
        docs_url="/api/docs" if s.docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if s.docs_enabled else None,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limited)
    register_exception_handlers(app)

    # order: last added runs first
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, hsts=s.is_production)
    if s.allowed_host_list and s.allowed_host_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.allowed_host_list)

    for r in (auth, ml, dashboard, chat, reports, reminders, locations, users):
        app.include_router(r.router, prefix=s.api_prefix)

    @app.get("/api/health", tags=["meta"])
    def health():
        """Liveness: the process is up."""
        return {"status": "ok", "version": APP_VERSION, "disclaimer": DISCLAIMER}

    @app.get("/api/ready", tags=["meta"])
    def ready():
        """Readiness: database reachable and the risk model loaded. Optional features are reported, not required."""
        from app.database.session import engine
        from app.ml.registry import get_registry
        from app.rag.retriever import get_retriever

        checks = {}
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.error("Readiness: database check failed: %s", exc)
            checks["database"] = "unavailable"
        try:
            get_registry().risk_model()
            checks["risk_model"] = "ok"
        except Exception:  # noqa: BLE001
            checks["risk_model"] = "missing"
        checks["knowledge_base"] = "ok" if get_retriever() is not None else "missing"
        checks["llm"] = "configured" if get_settings().gemini_api_key else "not_configured"
        ok = checks["database"] == "ok" and checks["risk_model"] == "ok"
        return JSONResponse({"status": "ready" if ok else "not_ready", "checks": checks, "version": APP_VERSION},
                            status_code=200 if ok else 503)

    return app


app = create_app()
