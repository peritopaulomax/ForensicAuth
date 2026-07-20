"""Shared pytest fixtures."""

import os
import sys
import uuid
from datetime import datetime

import pytest

pytestmark = []  # noqa: F401 — pacote de testes

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: testes end-to-end simulados")
    config.addinivalue_line("markers", "integration: testes de integracao com pesos/runtime")
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

# Ensure src/backend and scripts are on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from app.config import get_settings
from app.database import Base
from models.user import User
from models.case import Case
from models.evidence import Evidence
import models.case_share  # noqa: F401
import models.case_closure  # noqa: F401

# Use SQLite in-memory for unit tests
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _test_sqlite_fk(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Create a fresh database session for each test with rollback."""
    Base.metadata.create_all(bind=engine)

    from app.db_migrations import (
        ensure_analysis_job_progress_columns,
        ensure_case_custody_seal_columns,
        ensure_custody_lifecycle_tables,
        ensure_custody_signing_columns,
    )

    ensure_custody_signing_columns(engine)
    ensure_custody_lifecycle_tables(engine)
    ensure_analysis_job_progress_columns(engine)
    ensure_case_custody_seal_columns(engine)

    # Install SQLite trigger for immutability of custody_records
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            conn.execute(
                text("""
                    CREATE TRIGGER IF NOT EXISTS trg_custody_immutable
                    BEFORE UPDATE ON custody_records
                    BEGIN
                        SELECT RAISE(IGNORE);
                    END;
                """)
            )
            conn.commit()

    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden DB dependency."""
    from contextlib import asynccontextmanager

    from app.main import app
    from app.database import get_db

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(db_session):
    """Create a test perito user."""
    import bcrypt

    user = User(
        id=uuid.uuid4(),
        username="perito01",
        email="perito01@pf.gov.br",
        hashed_password=bcrypt.hashpw("Senha1234".encode(), bcrypt.gensalt()).decode(),
        role="perito",
        is_active=True,
        password_set=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_admin(db_session):
    """Create a test admin user."""
    import bcrypt

    user = User(
        id=uuid.uuid4(),
        username="admin01",
        email="admin01@pf.gov.br",
        hashed_password=bcrypt.hashpw("Admin1234".encode(), bcrypt.gensalt()).decode(),
        role="admin",
        is_active=True,
        password_set=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def inactive_user(db_session):
    """Create an inactive user."""
    import bcrypt

    user = User(
        id=uuid.uuid4(),
        username="inativo01",
        email="inativo01@pf.gov.br",
        hashed_password=bcrypt.hashpw("Senha1234".encode(), bcrypt.gensalt()).decode(),
        role="perito",
        is_active=False,
        password_set=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def provisioned_user(db_session):
    """User authorized by admin but without password set yet."""
    from services.user_service import unset_password_hash

    user = User(
        id=uuid.uuid4(),
        username="novo.perito",
        email="novo.perito@pf.gov.br",
        hashed_password=unset_password_hash(),
        password_set=False,
        role="perito",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_user):
    """Generate a valid JWT token for the test user."""
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(test_user.id), "role": test_user.role},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_auth_headers(test_admin):
    """Generate a valid JWT token for the test admin."""
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(test_admin.id), "role": test_admin.role},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def sample_case(db_session, test_user):
    """Create a sample case."""
    case = Case(
        id=uuid.uuid4(),
        protocol_number="CASO-2026-0001",
        title="Caso de Teste",
        description="Descrição do caso de teste",
        created_by=test_user.id,
        status="aberto",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


@pytest.fixture(scope="function")
def sample_evidence(db_session, sample_case, test_user):
    """Create a sample evidence record."""
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=sample_case.id,
        filename="teste.jpg",
        original_filename="foto_original.jpg",
        file_path="./uploads/teste.jpg",
        file_size=1024,
        file_type="imagem",
        mime_type="image/jpeg",
        sha256="a" * 64,
        uploaded_by=test_user.id,
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence
