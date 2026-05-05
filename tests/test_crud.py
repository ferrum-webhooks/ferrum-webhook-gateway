from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_register_user():
    response = client.post("/register", json={
        "email": "test@example.com",
        "password": "test123"
    })
    assert response.status_code == 200
    assert "id" in response.json()

def test_create_webhook():
    response = client.post("/webhooks", json={
        "url": "https://example.com",
        "event_type": "test"
    })
    assert response.status_code == 200
    assert response.json()["event_type"] == "test"

def test_create_event():
    response = client.post("/events", json={
        "payload": {"msg": "hello"},
        "event_type": "test"
    })
    assert response.status_code == 200
    assert "event_id" in response.json()