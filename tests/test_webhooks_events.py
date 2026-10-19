from app import db as app_db, models
from tests.conftest import signup

HOOK = {"url": "https://example.com/hook", "event_type": "order.created"}


def db():
    return app_db.get_session_local()()


def test_webhook_crud_and_secret(client, auth):
    r = client.post("/webhooks", json=HOOK, headers=auth)
    assert r.status_code == 201
    wh = r.json()
    assert wh["secret"].startswith("whsec_")
    assert "secret" not in client.get("/webhooks", headers=auth).json()[0]
    assert client.get(f"/webhooks/{wh['id']}", headers=auth).json()["secret"] == wh["secret"]

    r = client.patch(f"/webhooks/{wh['id']}", json={"event_type": "order.paid"}, headers=auth)
    assert r.json()["event_type"] == "order.paid"
    assert client.get("/webhooks", headers=auth).json()[0]["event_type"] == "order.paid"  # cache invalidated

    assert client.delete(f"/webhooks/{wh['id']}", headers=auth).status_code == 204
    assert client.get("/webhooks", headers=auth).json() == []
    assert client.get(f"/webhooks/{wh['id']}", headers=auth).status_code == 404


def test_everything_is_scoped_by_user(client):
    alice = signup(client, "alice@example.com")
    bob = signup(client, "bob@example.com")
    wh = client.post("/webhooks", json=HOOK, headers=alice).json()
    ev = client.post("/events", json={"event_type": "order.created", "payload": {"a": 1}}, headers=alice).json()

    assert client.get("/webhooks", headers=bob).json() == []
    assert client.get(f"/webhooks/{wh['id']}", headers=bob).status_code == 404
    assert client.patch(f"/webhooks/{wh['id']}", json={"url": "https://evil.example/x"}, headers=bob).status_code == 404
    assert client.delete(f"/webhooks/{wh['id']}", headers=bob).status_code == 404
    assert client.get("/events", headers=bob).json() == []
    assert client.get(f"/events/{ev['event_id']}", headers=bob).status_code == 404
    assert client.get(f"/deliveries/{ev['event_id']}", headers=bob).status_code == 404
    assert client.post(f"/retry/{ev['event_id']}", headers=bob).status_code == 404
    assert client.get("/deliveries", headers=bob).json() == []

    # Bob's events never fan out to Alice's webhooks
    r = client.post("/events", json={"event_type": "order.created", "payload": {}}, headers=bob).json()
    assert r["deliveries"] == 0 and r["status"] == "no_subscribers"


def test_ingest_writes_event_deliveries_and_outbox_atomically(client, auth):
    client.post("/webhooks", json=HOOK, headers=auth)
    client.post("/webhooks", json={**HOOK, "url": "https://example.org/other"}, headers=auth)
    client.post("/webhooks", json={**HOOK, "event_type": "unrelated"}, headers=auth)

    r = client.post("/events", json={"event_type": "order.created", "payload": {"id": 7}}, headers=auth)
    assert r.status_code == 202
    body = r.json()
    assert body["event_id"].startswith("evt_") and body["deliveries"] == 2

    s = db()
    assert s.query(models.Delivery).count() == 2
    outbox = s.query(models.Outbox).all()
    assert len(outbox) == 2 and all(o.published_at is None for o in outbox)
    s.close()


def test_idempotency_key(client, auth):
    client.post("/webhooks", json=HOOK, headers=auth)
    body = {"event_type": "order.created", "payload": {"id": 1}}
    h = {**auth, "Idempotency-Key": "abc-123"}

    first = client.post("/events", json=body, headers=h)
    again = client.post("/events", json=body, headers=h)
    assert first.status_code == 202 and again.status_code == 200
    assert again.headers["idempotent-replayed"] == "true"
    assert again.json()["event_id"] == first.json()["event_id"]

    s = db()
    assert s.query(models.Event).count() == 1
    assert s.query(models.Outbox).count() == 1  # the retry did not enqueue a second delivery
    s.close()

    clash = client.post("/events", json={**body, "payload": {"id": 2}}, headers=h)
    assert clash.status_code == 422

    # same key, different user: independent namespace
    other = signup(client, "other@example.com")
    r = client.post("/events", json=body, headers={**other, "Idempotency-Key": "abc-123"})
    assert r.status_code == 202 and r.json()["event_id"] != first.json()["event_id"]

    # no key => every request is a new event
    a = client.post("/events", json=body, headers=auth).json()["event_id"]
    b = client.post("/events", json=body, headers=auth).json()["event_id"]
    assert a != b


def test_validation(client, auth):
    assert client.post("/events", json={"event_type": "", "payload": {}}, headers=auth).status_code == 422
    assert client.post("/events", json={"event_type": "x", "payload": "str"}, headers=auth).status_code == 422
    assert client.post("/events", json={"event_type": "x", "payload": {}},
                       headers={**auth, "Idempotency-Key": "k" * 300}).status_code == 400
    assert client.post("/webhooks", json={"url": "not-a-url", "event_type": "x"}, headers=auth).status_code == 422


def test_deliveries_and_replay(client, auth):
    wh = client.post("/webhooks", json=HOOK, headers=auth).json()
    ev = client.post("/events", json={"event_type": "order.created", "payload": {}}, headers=auth).json()

    # simulate the worker having dead-lettered the delivery
    s = db()
    d = s.query(models.Delivery).one()
    d.status, d.retries, d.moved_to_dlq, d.error_message = "dead_letter", 5, 1, "HTTP 500"
    s.add(models.DeliveryAttempt(delivery_id=d.id, attempt=1, status="failed", response_code=500, latency_ms=12))
    s.query(models.Event).update({"status": "failed"})
    s.commit(); s.close()

    got = client.get(f"/deliveries/{ev['event_id']}", headers=auth).json()
    assert got[0]["status"] == "dead_letter" and got[0]["webhook_id"] == wh["id"]
    assert got[0]["attempts"][0]["response_code"] == 500
    assert [x["status"] for x in client.get("/deliveries?status=dead_letter", headers=auth).json()] == ["dead_letter"]
    assert client.get("/deliveries?status=success", headers=auth).json() == []

    r = client.post(f"/retry/{ev['event_id']}", headers=auth)
    assert r.status_code == 202 and r.json()["replayed_deliveries"] == 1
    s = db()
    d = s.query(models.Delivery).one()
    assert d.status == "pending" and d.retries == 0
    assert s.query(models.Outbox).count() == 2  # original + replay
    s.close()

    # nothing failed any more: replay is a no-op, successes are never re-sent
    assert client.post(f"/events/{ev['event_id']}/replay", headers=auth).json()["replayed_deliveries"] == 0


def test_ingest_records_traceparent_for_the_worker(client, auth):
    """The ingest request's trace context is stored on the delivery and outbox row, so the
    worker's delivery/retry spans join the same trace."""
    from opentelemetry import trace
    client.post("/webhooks", json=HOOK, headers=auth)
    client.post("/events", json={"event_type": "order.created", "payload": {}}, headers=auth)
    s = db()
    tp = s.query(models.Outbox).one().traceparent
    assert tp and tp.startswith("00-") and len(tp.split("-")) == 4
    assert s.query(models.Delivery).one().traceparent == tp
    s.close()
