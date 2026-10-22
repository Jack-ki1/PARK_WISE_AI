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


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
