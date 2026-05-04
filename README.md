# Ferrum — Webhook Gateway Service (Phase 5)

## Overview

This repository contains the **Gateway Service** of Ferrum — a cloud-native webhook relay system.

The gateway is responsible for:

* receiving incoming API requests
* validating and persisting data
* pushing events to a queue for asynchronous processing

This service acts as the **ingress layer** of the system and is designed to be fast, stateless (logically), and horizontally scalable.

---

## Architecture Context

```
Client → Gateway → PostgreSQL → Redis Queue → Worker → Webhook Endpoint
```

This service:
- Writes events to DB
- Pushes `event_id` to Redis queue
- does not process events

---

## Responsibilities

### Gateway DOES:

* Handle HTTP requests (FastAPI)
* Validate input using Pydantic
* Persist data in PostgreSQL
* Serve webhook management APIs
* Push events to Redis queue
* Serve cached reads (Redis)
* Emit structured logs and metrics

---

### Gateway DOES NOT:

* Deliver webhooks
* Retry failed deliveries
* Process events asynchronously
* Guarantee delivery success

---

## Dependencies

* Python 3.10+
* PostgreSQL
* Redis
* Python packages:

  * fastapi
  * uvicorn
  * sqlalchemy
  * psycopg2-binary
  * redis
  * passlib
  * python-dotenv
  * prometheus-client
  * python-json-logger

---

## Setup Instructions

---
### 1. Clone repository

```bash
git clone <your-repo-url>
cd webhook-gateway
```

---

### 2. Environment Configuration
```text
DB_HOST 
DB_PORT 
DB_USER 
DB_PASSWORD 
DB_NAME 
REDIS_HOST 
REDIS_PORT
```

---

### 3. Run in Docker
```bash
docker build -t ferrum-gateway .
docker run -p 8000:8000 ferrum-gateway
```

---

## API Endpoints

---

### Auth

#### Register User

```http
POST /register
```

Request:

```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

---

### Webhooks

#### Create Webhook

```http
POST /webhooks
```

Request:

```json
{
  "url": "https://example.com/webhook",
  "event_type": "test"
}
```

---

#### List Webhooks

```http
GET /webhooks
```

* Uses Redis cache (cache-aside pattern)

---

### Events

#### Create Event

```http
POST /events
```

Request:

```json
{
  "payload": { "key": "value" },
  "event_type": "test"
}
```

Effect:

* Event stored in DB
* Event ID pushed to queue
* Worker picks it up asynchronously

---

## Internal Workflow

---

### 1. Request Handling

* FastAPI receives request
* Pydantic validates input
* CRUD layer handles DB interaction

---

### 2. Event Ingestion

```text
Request → DB write → Queue push → Response
```

* Event stored with status = `pending`
* Only `event_id` pushed to queue (minimal contract)

---

### 3. Caching (Cache-Aside)

For `GET /webhooks`:

```text
Check cache → miss → DB → set cache → return
```

On mutation:

```text
Invalidate cache
```

---

### 4. Queue Publishing

Redis LIST used as queue:

* Producer → `LPUSH`
* Worker → `BRPOP`

Payload:

```json
{
  "event_id": <id>,
  "request_id": "<uuid>"
}
```

---

## Observability

---

### Request Correlation

Each incoming request is assigned a:

```X-Request-ID```

This ID is:

* generated at ingress
* propagated to queue
* used by worker for tracing

### Request Latency Middleware

Every response includes:

```X-Process-Time: <seconds>```

This measures:

* request lifecycle latency
* baseline for performance comparisons

### Logging

Structured JSON logs include:

* request lifecycle
* cache hits/misses
* queue push events

Fields:
```
service, request_id, event_id, latency, status_code
```

### Metrics (Prometheus)
Exposed at:
```
GET /metrics
```
Metrics include:

* `gateway_requests_total`
* `gateway_request_latency_seconds`

These enable:

* traffic monitoring
* latency distribution analysis
---

## Security

---

### Password Hashing

* argon2
* Stored as `password_hash`

---

### Input Validation

* Enforced via Pydantic schemas
* Prevents malformed data

---

## Failure Handling

---

### Redis Failure

* Cache operations wrapped in try/catch
* Falls back to DB

---

### DB Failure

* Request fails (no fallback)
* Expected behavior for now

---

## Known Limitations

---

### 1. No authentication yet (temporary)

* `user_id=1` is hardcoded
* JWT auth planned in future phases

---

### 2. No rate limiting

* System is vulnerable to abuse

---

### 3. No request throttling

* Could overwhelm DB under load

---

### 4. No schema migrations in runtime

* Alembic required in containerized setup

---

### 5. Cache inconsistency window

* Short-lived stale reads possible

---

### 6. No distributed tracing

* Only `request_id` based correlation exists

## Design Decisions

---

### Why push only `event_id` to queue?

* Reduces message size
* Avoids duplication
* Ensures DB is source of truth

---

### Why Redis for queue?

* Simplicity
* Fast setup
* Sufficient for early phases

---

### Why synchronous DB?

* Simpler mental model
* Easier debugging
* Will evolve later

---

## Deliberate Gaps (Future Work)

* JWT authentication
* Rate limiting
* Async DB driver
* Message durability guarantees
* Schema migration automation
* Horizontal scaling
* Distributed tracing (OpenTelemetry)
* Alerting & Dashboards (Grafana)

---

## Key Concepts Demonstrated

* API design with FastAPI
* ORM-based persistence
* Cache-aside pattern
* Producer-consumer model
* Queue-based decoupling
* Request lifecycle measurement
* Structured Logging
* Metrics Instrumentation via Prometheus
* Cross-service request tracing

---

## Status

🚧 Phase 5 — Observability
✅ Logs + Metrics + Correlation implemented
✅ End-to-end async processing working

---

## Next Steps

* Retry mechanism (worker)
* Backoff strategy
* Delivery attempt tracking
* System reliability improvements

---

