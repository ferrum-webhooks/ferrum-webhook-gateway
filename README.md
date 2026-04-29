# Ferrum — Webhook Gateway Service (Phase 3)

## Overview

This repository contains the **Gateway Service** of Ferrum — a cloud-native webhook relay system.

The gateway is responsible for:

* receiving incoming API requests
* validating and persisting data
* pushing events to a queue for asynchronous processing

This service acts as the **ingress layer** of the system and is designed to be fast, stateless (logically), and horizontally scalable.

---

## Architecture Context

Ferrum currently consists of two services:

### 1. Gateway (`webhook-gateway`) ← *this repo*

* Accepts API requests
* Stores users, webhooks, and events
* Pushes events to queue

### 2. Worker (`webhook-worker`)

* Consumes events from queue
* Delivers webhooks
* Tracks delivery outcomes

---

## System Flow

```text
Client → Gateway → PostgreSQL → Redis Queue → Worker → Webhook Endpoint
```

---

## Responsibilities

### Gateway DOES:

* Handle HTTP requests (FastAPI)
* Validate input using Pydantic
* Persist data in PostgreSQL
* Serve webhook management APIs
* Push events to Redis queue
* Serve cached reads (Redis)

---

### Gateway DOES NOT:

* Deliver webhooks
* Retry failed deliveries
* Process events asynchronously
* Guarantee delivery success

---

## Project Structure

```text
webhook-gateway/
  app/
    main.py              # API routes + middleware
    db.py                # DB connection and session
    models.py            # SQLAlchemy models
    schemas.py           # Pydantic schemas
    deps.py              # Dependency injection (DB session)
    cache.py             # Redis cache + queue producer
    security.py          # Password hashing
    crud/
      user.py
      webhook.py
      event.py
  requirements.txt
  README.md
```

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

---

## Setup Instructions

---

### 1. Clone repository

```bash
git clone <your-repo-url>
cd webhook-gateway
```

---

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

---

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Configure environment

Ensure:

* PostgreSQL is running
* Redis is running on:

```text
localhost:6379
```

---

### 5. Run server

```bash
uvicorn app.main:app --reload
```

Server will start at:

```text
http://127.0.0.1:8000
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
  "event_id": <id>
}
```

---

## Observability

---

### Request Latency Middleware

Every response includes:

```text
X-Process-Time: <seconds>
```

This measures:

* request lifecycle latency
* baseline for performance comparisons

---

### Logging

Logs include:

* request completion time
* cache hits/misses
* queue push events

---

## Security

---

### Password Hashing

* SHA256 pre-hash + bcrypt
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

## Deliberate Gaps (Phase 4+ Work)

* JWT authentication
* Rate limiting
* Async DB driver
* Message durability guarantees
* Schema migration automation
* Horizontal scaling

---

## Key Concepts Demonstrated

* API design with FastAPI
* ORM-based persistence
* Cache-aside pattern
* Producer-consumer model
* Queue-based decoupling
* Request lifecycle measurement

---

## Status

🚧 Phase 3 — In Progress
✅ Gateway fully integrated with queue and worker

---

## Next Steps

* Retry mechanism (worker)
* Backoff strategy
* Delivery attempt tracking
* System reliability improvements

---

## Summary

The gateway has evolved from:

```text
Simple CRUD API
```

to:

```text
High-throughput event ingestion layer
```

It now serves as the **entry point of a distributed, asynchronous system**, optimized for:

* low latency
* scalability
* decoupled processing

---
