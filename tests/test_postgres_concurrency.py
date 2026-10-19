"""Regression test for the connection-pool / threadpool deadlock (needs a real, disposable Postgres).

  TEST_DATABASE_URL=postgresql://user:pw@localhost:5432/ferrum_test  python -m pytest tests/test_postgres_concurrency.py

Setup mirrors production pressure at small scale: 120 concurrent requests, 4 DB connections, 6 threads.
Without SessionReleasingRoute (connection released only at dependency teardown) this scenario completed 6 of 120
requests in 57 s; with it, all 120 complete in well under a second.
"""
import asyncio
import os
import time

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"),
                                reason="needs TEST_DATABASE_URL pointing at a real, disposable Postgres")

N_REQUESTS = 120


def _run(app, headers, dependency_override=None, method="GET", path="/events"):
    import anyio.to_thread
    import httpx

    if dependency_override:
        from app.deps import get_db
        app.dependency_overrides[get_db] = dependency_override

    async def go():
        anyio.to_thread.current_default_thread_limiter().total_tokens = 6      # tiny threadpool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=30) as c:
            t0 = time.time()
            if method == "POST":
                reqs = [c.post(path, json={"event_type": "e", "payload": {"i": i}}, headers=headers) for i in range(N_REQUESTS)]
            else:   # reads leave their transaction (and connection) open until the session is closed in teardown
                reqs = [c.get(path, headers=headers) for _ in range(N_REQUESTS)]
            rs = await asyncio.gather(*reqs)
            return rs, time.time() - t0

    try:
        return asyncio.run(go())
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def tiny_pool(client):
    """Replace the engine with a 4-connection pool and a 3 s timeout (restored afterwards)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import db as app_db
    old_engine, old_factory = app_db._engine, app_db._session_factory
    eng = create_engine(os.environ["TEST_DATABASE_URL"], pool_size=4, max_overflow=0, pool_timeout=3)
    app_db._engine = eng
    app_db._session_factory = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=eng)
    yield
    eng.dispose()
    app_db._engine, app_db._session_factory = old_engine, old_factory


def test_ingest_burst_far_above_pool_size_completes(client, auth, tiny_pool):
    from app.main import app
    client.post("/webhooks", json={"url": "https://93.184.216.34/h", "event_type": "e"}, headers=auth)
    rs, elapsed = _run(app, auth, method="POST")
    codes = [r.status_code for r in rs]
    assert codes.count(202) == N_REQUESTS, f"{set(codes)} in {elapsed:.1f}s"
    assert elapsed < 20


def test_read_burst_far_above_pool_size_completes(client, auth, tiny_pool):
    from app.main import app
    rs, elapsed = _run(app, auth)                                  # GET /events
    codes = [r.status_code for r in rs]
    assert codes.count(200) == N_REQUESTS, f"{set(codes)} in {elapsed:.1f}s"
    assert elapsed < 20


def test_every_connection_is_returned_to_the_pool_after_a_burst(client, auth, tiny_pool):
    from app import db as app_db
    from app.main import app
    _run(app, auth)
    _run(app, auth, method="POST")
    assert app_db._engine.pool.checkedout() == 0


def test_every_sync_route_releases_its_session_in_its_own_thread():
    """Structural guard: if someone registers a route outside SessionReleasingRoute the deadlock can return."""
    import inspect
    from fastapi.routing import APIRoute
    from app.main import app, SessionReleasingRoute
    for r in app.routes:
        if isinstance(r, APIRoute) and not inspect.iscoroutinefunction(r.endpoint.__wrapped__ if hasattr(r.endpoint, "__wrapped__") else r.endpoint):
            assert isinstance(r, SessionReleasingRoute), r.path
            assert hasattr(r.endpoint, "__wrapped__"), f"{r.path} is not wrapped"
