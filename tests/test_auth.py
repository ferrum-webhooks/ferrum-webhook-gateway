import time

import jwt
from tests.conftest import signup


def test_protected_routes_require_token(client):
    for method, path in [("get", "/webhooks"), ("post", "/events"), ("get", "/events"),
                         ("get", "/deliveries"), ("post", "/retry/evt_x")]:
        r = getattr(client, method)(path)
        assert r.status_code == 401, (method, path)
        assert r.headers["www-authenticate"] == "Bearer"


def test_bad_and_expired_tokens_rejected(client):
    assert client.get("/webhooks", headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = jwt.encode({"sub": "1", "exp": int(time.time()) - 10}, "x" * 40, algorithm="HS256")
    assert client.get("/webhooks", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    wrong_key = jwt.encode({"sub": "1", "exp": int(time.time()) + 60}, "y" * 40, algorithm="HS256")
    assert client.get("/webhooks", headers={"Authorization": f"Bearer {wrong_key}"}).status_code == 401
    # alg=none must never be accepted
    none_tok = jwt.encode({"sub": "1", "exp": int(time.time()) + 60}, None, algorithm="none")
    assert client.get("/webhooks", headers={"Authorization": f"Bearer {none_tok}"}).status_code == 401


def test_register_login(client):
    signup(client)
    assert client.post("/register", json={"email": "a@example.com", "password": "another-pass"}).status_code == 409
    assert client.post("/login", json={"email": "a@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/login", json={"email": "nobody@example.com", "password": "whatever-pw"}).status_code == 401
    assert client.post("/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_auth_endpoints_are_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr("app.deps.take_auth_token", lambda ip: (False, 7))
    for path in ("/register", "/login"):
        r = client.post(path, json={"email": "a@example.com", "password": "correct-horse"})
        assert r.status_code == 429 and r.headers["retry-after"] == "7"


def test_hash_concurrency_is_bounded_and_old_hashes_still_verify():
    from passlib.context import CryptContext
    from app import security
    old = CryptContext(schemes=["argon2"]).hash("hunter2hunter2")   # default (64 MiB) params
    assert security.verify_password("hunter2hunter2", old)
    assert not security.verify_password("wrong-password", old)
    assert security.pwd_context.hash("x" * 10).startswith("$argon2id$v=19$m=19456,t=2,p=1$")
