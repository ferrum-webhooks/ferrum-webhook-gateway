# Ferrum — Webhook Relay (Phase 3: Gateway Service)

## Overview

This repository contains the **Gateway Service** of Ferrum, responsible for:

* accepting API requests
* validating and storing events
* enqueueing events for asynchronous processing

This marks the transition from a monolithic system to an **event-driven architecture**.

---

## Architecture

Client → FastAPI (Gateway) → PostgreSQL → Redis Queue → Worker (separate service)

---

## Responsibilities

### Gateway handles:

* User registration
* Webhook management
* Event ingestion
* Caching (Redis)
* Queue production

### Gateway does NOT:

* Deliver webhooks
* Handle retries
* Process events

---

## Key Features

### API Endpoints

* `POST /register`
* `POST /webhooks`
* `GET /webhooks`
* `POST /events`

---

### Event Flow

1. Client sends event
2. Event stored in PostgreSQL
3. Event ID pushed to Redis queue
4. Worker service processes asynchronously

---

### Queue Design

* Redis used as message broker
* Queue type: LIST
* Pattern:

  * Producer: `LPUSH`
  * Consumer: `BRPOP`
* Message format:

```json
{
  "event_id": 123
}
```

---

## Caching Layer

* Cache-aside pattern
* Cached endpoint:

  * `GET /webhooks`
* TTL: 60 seconds

### Failure Handling

* Redis failures do NOT break API
* System falls back to DB
* Cache errors are logged

---

## Performance Observations

| Scenario   | Latency |
| ---------- | ------- |
| Cache MISS | ~22 ms  |
| Cache HIT  | ~1.2 ms |

---

## Database

### Tables

* users
* webhooks
* events
* deliveries

### Migrations

* Managed via Alembic
* No runtime schema creation

---

## Observability

* Request latency via `X-Process-Time`
* Logging:

  * cache hit/miss/error
  * queue push events

---

## Known Limitations

* No authentication (user_id hardcoded)
* No worker integration yet
* No retry mechanism
* No delivery tracking per attempt
* Synchronous DB access (blocking)

---

## Next Steps (Phase 3 Continuation)

* Build `webhook-worker` service
* Consume queue events
* Fetch event from DB
* Deliver webhook via HTTP POST
* Track delivery status

---

## Key Concepts

* Event-driven architecture
* Asynchronous processing
* Decoupling via queues
* Cache-aside pattern
* Graceful degradation

---

## Status

🚧 Phase 3 (Gateway) — In Progress
➡️ Next: Worker Service + Delivery System
