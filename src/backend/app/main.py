"""FastAPI application entry point."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base
from app.db_migrations import (
    ensure_analysis_job_progress_columns,
    ensure_analysis_job_reproducibility_columns,
    ensure_case_custody_seal_columns,
    ensure_case_custody_seal_values,
    ensure_case_soft_delete_columns,
    ensure_case_storage_mode_column,
    ensure_migrate_analista_to_perito,
    ensure_migrate_em_andamento_to_aberto,
    ensure_custody_chain_sequence_column,
    ensure_custody_job_fk_on_delete_set_null,
    ensure_custody_lifecycle_tables,
    ensure_custody_signing_columns,
    ensure_evidence_soft_delete_columns,
    ensure_password_set_column,
)

settings = get_settings()


def _run_alembic_upgrade() -> None:
    """Run Alembic migrations in production environments."""
    import subprocess
    import sys

    from app.config import get_settings

    alembic_ini = Path(__file__).resolve().parents[3] / "alembic.ini"
    if not alembic_ini.is_file():
        logger.warning("alembic.ini nao encontrado; pulando migracoes")
        return
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
            check=True,
            cwd=str(alembic_ini.parent),
            capture_output=True,
            text=True,
        )
        logger.info("Migracoes Alembic aplicadas com sucesso")
    except subprocess.CalledProcessError as exc:
        logger.error("Falha ao aplicar migracoes Alembic: %s", exc.stderr)
        raise RuntimeError("Falha em migracoes Alembic") from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    if settings.ENVIRONMENT == "production":
        _run_alembic_upgrade()
    else:
        # Dev/test: keep legacy bootstrap for compatibility
        Base.metadata.create_all(bind=engine)

    # Legacy data migrations and column additions remain idempotent
    ensure_password_set_column(engine)
    ensure_evidence_soft_delete_columns(engine)
    ensure_case_soft_delete_columns(engine)
    ensure_custody_job_fk_on_delete_set_null(engine)
    ensure_custody_chain_sequence_column(engine)
    ensure_custody_signing_columns(engine)
    ensure_custody_lifecycle_tables(engine)
    ensure_analysis_job_progress_columns(engine)
    ensure_analysis_job_reproducibility_columns(engine)
    ensure_case_storage_mode_column(engine)
    ensure_case_custody_seal_columns(engine)
    ensure_case_custody_seal_values(engine)
    ensure_migrate_analista_to_perito(engine)
    ensure_migrate_em_andamento_to_aberto(engine)

    from core.preview_cleanup_scheduler import start_daily_preview_cleanup

    cleanup_task = start_daily_preview_cleanup(settings)
    try:
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
        # Shutdown
        engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS
cors_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
cors_headers = ["*"]
if settings.ENVIRONMENT == "production":
    cors_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    cors_headers = [
        "Authorization",
        "Content-Type",
        "X-Requested-With",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)


@app.get("/health")
def health_check():
    from core.legacy.camo.camo_warmup import camo_warmup_status
    from core.legacy.effort.effort_warmup import effort_warmup_status
    from core.legacy.iapl.iapl_warmup import iapl_warmup_status
    from core.legacy.safe.safe_warmup import safe_warmup_status
    from core.technique_runtime import technique_runtime_status

    zero_ok, zero_reason = technique_runtime_status("zero_grid")
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "capabilities": {
            "zero_grid": {"available": zero_ok, "reason": zero_reason or None},
            "effort_warmup": effort_warmup_status(),
            "safe_warmup": safe_warmup_status(),
            "camo_warmup": camo_warmup_status(),
            "iapl_warmup": iapl_warmup_status(),
        },
    }


from api.v1.endpoints import (
    auth,
    analysis,
    audit,
    evidences,
    cases,
    users,
    prnu,
    references,
    case_shares,
    case_transfer,
    peritus_transfer,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(case_shares.router, prefix="/api/v1", tags=["case-shares"])
app.include_router(case_transfer.router, prefix="/api/v1", tags=["case-transfer"])
app.include_router(peritus_transfer.router, prefix="/api/v1", tags=["peritus-transfer"])
app.include_router(cases.router, prefix="/api/v1", tags=["cases"])
app.include_router(evidences.router, prefix="/api/v1", tags=["evidences"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(references.router, prefix="/api/v1", tags=["references"])
app.include_router(prnu.router, prefix="/api/v1", tags=["prnu"])
app.include_router(audit.router, prefix="/api/v1", tags=["audit"])

# from api.v1.endpoints import cases, evidence, reports, audit
# app.include_router(cases.router, prefix="/api/v1/cases", tags=["cases"])
