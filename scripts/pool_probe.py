"""Reproduce (or verify the fix for) the connection-pool / thread-pool deadlock, in-process, in seconds.

    createdb -h localhost -p 5544 -U ferrum_user ferrum_test         # a disposable Postgres database
    TEST_DATABASE_URL=postgresql://ferrum_user@localhost:5544/ferrum_test \
        python scripts/pool_probe.py [--legacy] [--requests 120] [--threads 6] [--pool 4]

Fires N concurrent GET /events at the real ASGI app with a deliberately small DB pool and thread budget.
  default   : the current code (handlers release their connection themselves)   -> every request succeeds in milliseconds
  --legacy  : releases the connection only at dependency teardown (the old behaviour) -> requests stall until pool_timeout
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))      # run from anywhere

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET", "x" * 40)
os.environ.setdefault("ALLOW_PRIVATE_WEBHOOK_TARGETS", "true")

import anyio.to_thread
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as app_db, models

ap = argparse.ArgumentParser()
ap.add_argument("--legacy", action="store_true")
ap.add_argument("--requests", type=int, default=120)
ap.add_argument("--threads", type=int, default=6)
ap.add_argument("--pool", type=int, default=4)
ap.add_argument("--timeout", type=float, default=3.0, help="pool_timeout seconds")
ap.add_argument("--path", default="/events", help="GET path to hammer; /readyz uses the DB but has no response_model")
args = ap.parse_args()

url = os.environ["TEST_DATABASE_URL"]
assert "test" in url.rsplit("/", 1)[-1], "use a disposable database whose name contains 'test'"
eng = create_engine(url, pool_size=args.pool, max_overflow=0, pool_timeout=args.timeout)
app_db._engine = eng
app_db._session_factory = sessionmaker(autoflush=False, expire_on_commit=False, bind=eng)
app_db.Base.metadata.drop_all(eng); app_db.Base.metadata.create_all(eng)

import app.deps as deps
deps.take_token = lambda uid: (True, 0)                      # no Redis needed
from app.main import app
from app.security import create_access_token

if args.legacy:
    # undo SessionReleasingRoute and use a SYNC generator dependency, exactly as the code was before the fix
    for r in app.routes:
        wrapped = getattr(getattr(r, "endpoint", None), "__wrapped__", None)
        if wrapped is not None:
            r.endpoint = wrapped
            r.dependant.call = wrapped

    def sync_get_db():
        db = app_db.get_session_local()()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[deps.get_db] = sync_get_db

s = app_db._session_factory()
u = models.User(email="probe@example.com", password_hash="x"); s.add(u); s.commit(); uid = u.id; s.close()
H = {"Authorization": "Bearer " + create_access_token(uid)}


async def main():
    anyio.to_thread.current_default_thread_limiter().total_tokens = args.threads
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=60) as c:
        t0 = time.time()
        rs = await asyncio.gather(*[c.get(args.path, headers=H) for _ in range(args.requests)])
        dt = time.time() - t0
    codes = [r.status_code for r in rs]
    mode = "legacy (release at teardown)" if args.legacy else "current (release in handler)"
    print(f"{mode:30s} {args.path:8s} requests={args.requests} threads={args.threads} pool={args.pool}  ok={codes.count(200)}  "
          f"503={codes.count(503)}  elapsed={dt:.1f}s  pool_checked_out_after={eng.pool.checkedout()}")

asyncio.run(main())
