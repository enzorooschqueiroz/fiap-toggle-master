import os
from unittest import mock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("AUTH_SERVICE_URL", "http://auth.test")
os.environ.setdefault("MASTER_KEY", "master-test")

with mock.patch("psycopg2.pool.SimpleConnectionPool"):
    import app as flag_app  # noqa: E402

ADMIN = {"Authorization": "Bearer master-test"}


@pytest.fixture
def client():
    flag_app.chaos.set_rate(0)
    flag_app.app.testing = True
    yield flag_app.app.test_client()
    flag_app.chaos.set_rate(0)


def test_health_exempt_under_chaos(client):
    flag_app.chaos.set_rate(100)
    assert client.get("/health").status_code == 200


def test_chaos_requires_master_key(client):
    assert client.post("/admin/chaos", json={"error_rate": 100}).status_code == 401
    wrong = {"Authorization": "Bearer outra"}
    assert client.post("/admin/chaos", json={"error_rate": 100}, headers=wrong).status_code == 401


def test_chaos_makes_flags_fail(client):
    assert client.post("/admin/chaos", json={"error_rate": 100}, headers=ADMIN).status_code == 200
    assert client.get("/flags").status_code == 500


def test_chaos_rejects_out_of_range(client):
    assert client.post("/admin/chaos", json={"error_rate": 150}, headers=ADMIN).status_code == 400
    assert client.post("/admin/chaos", json={"error_rate": "x"}, headers=ADMIN).status_code == 400
