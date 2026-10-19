import time

import pytest
import redis

from app import ratelimit


def _redis_up():
    try:
        return redis.Redis(socket_connect_timeout=0.3).ping()
    except Exception:
        return False


def test_429_with_retry_after(client, auth, monkeypatch):
    monkeypatch.setattr("app.deps.take_token", lambda uid: (False, 3))
    r = client.get("/webhooks", headers=auth)
    assert r.status_code == 429 and r.headers["retry-after"] == "3"


def test_fails_open_when_redis_is_down(monkeypatch):
    class Boom:
        def register_script(self, *_):
            raise redis.exceptions.ConnectionError("down")
    monkeypatch.setattr(ratelimit, "redis_client", Boom())
    monkeypatch.setattr(ratelimit, "_script", None)
    assert ratelimit.take_token(1) == (True, 0)


@pytest.mark.skipif(not _redis_up(), reason="needs a local redis on :6379")
def test_token_bucket_against_real_redis(monkeypatch):
    r = redis.Redis(decode_responses=True)
    monkeypatch.setattr(ratelimit, "redis_client", r)
    monkeypatch.setattr(ratelimit, "_script", None)
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_CAPACITY", 3)
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_REFILL_PER_SEC", 5.0)
    uid = 987654
    r.delete(f"ratelimit:user:{uid}")

    assert [ratelimit.take_token(uid)[0] for _ in range(3)] == [True, True, True]
    allowed, retry = ratelimit.take_token(uid)
    assert allowed is False and retry >= 1
    time.sleep(0.45)                       # ~2 tokens refill at 5/s
    assert ratelimit.take_token(uid)[0] is True
    assert ratelimit.take_token(uid)[0] is True
    assert ratelimit.take_token(uid)[0] is False
    r.delete(f"ratelimit:user:{uid}")
