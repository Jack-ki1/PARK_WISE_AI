import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Use an isolated database/media directory for tests. No videos or metrics are seeded.
ROOT = Path(__file__).resolve().parents[2]
TEST_DATA = ROOT / ".test-data"
TEST_DATA.mkdir(exist_ok=True)
(TEST_DATA / "parkwise-test.db").unlink(missing_ok=True)
sys.path.insert(0, str(ROOT / "backend"))
os.environ["PARKWISE_DATABASE_URL"] = f"sqlite:///{(TEST_DATA / 'parkwise-test.db').as_posix()}"
os.environ["PARKWISE_DATA_DIR"] = str(TEST_DATA)

from app.main import app  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    """Wipe all tables and in-memory runtime state before every test.

    Tests must never see rows created by a previous test (quota checks, role
    checks and analytics all read the database).
    """
    from app.api import ws_tickets
    from app.security import rate_limiter
    from app.services.live_stream import manager

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    manager.shutdown()
    ws_tickets.clear()
    # Mutating routes are rate limited per API key/IP; without this the shared
    # bucket fills across tests and later cases fail with a spurious 429.
    rate_limiter._hits.clear()
    yield
    manager.shutdown()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
