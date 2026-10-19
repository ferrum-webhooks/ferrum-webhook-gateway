import os

os.environ["TESTING"] = "true"
os.environ.setdefault("JWT_SECRET", "x" * 40)
os.environ["ALLOW_PRIVATE_WEBHOOK_TARGETS"] = "true"   # other tests use arbitrary hostnames; test_ssrf.py turns it off

import pytest


def _guard_test_database():
    """create_all/drop_all run against TEST_DATABASE_URL on every test: refuse anything not obviously disposable."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url and "test" not in url.rsplit("/", 1)[-1].lower():
        raise RuntimeError("TEST_DATABASE_URL must point at a disposable database whose name contains 'test'")


_guard_test_database()
from fastapi.testclient import TestClient

from app import db as app_db


@pytest.fixture()
def client(monkeypatch):
    from app import models  # noqa: F401  (tables must be registered on Base.metadata before drop_all/create_all)
    engine = app_db.get_engine()
    app_db.Base.metadata.drop_all(engine)
    app_db.Base.metadata.create_all(engine)

    # Redis is not available in unit tests: in-memory cache + permissive limiter.
    store = {}
    monkeypatch.setattr("app.main.get_cache", lambda k: store.get(k))
    monkeypatch.setattr("app.main.set_cache", lambda k, v, ttl=60: store.__setitem__(k, v))
    monkeypatch.setattr("app.main.delete_cache", lambda k: store.pop(k, None))
    monkeypatch.setattr("app.deps.take_token", lambda uid: (True, 0))
    monkeypatch.setattr("app.deps.take_auth_token", lambda ip: (True, 0))

    from app.main import app
    with TestClient(app) as c:
        yield c


def signup(client, email="a@example.com", password="correct-horse"):
    r = client.post("/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture()
def auth(client):
    return signup(client)
