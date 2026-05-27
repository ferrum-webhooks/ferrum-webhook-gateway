# Ferrum — Webhook Gateway Service 

## Overview

This repository contains the **Gateway Service** of Ferrum — a cloud-native webhook relay system. 

The gateway is responsible for:

| **Responsibility** | **Description** |
| --- | --- |
| API ingress |	accepts webhook registrations and events |
Event persistence	| stores events in PostgreSQL |
Queue publishing |	publishes events to Redis |
Request validation |	validates incoming payloads |
Metrics exposure | exposes Prometheus metrics |
Observability correlation |	injects request IDs and structured logs |
Distributed coordination |	communicates with worker infrastructure |

This service acts as the **ingress layer** of the system and is designed to be fast, stateless (logically), and horizontally scalable. It evolved from a single synchronous FastAPI application into a production oriented distributed system implementing:

* asynchronous event delivery
* Redis-backed queueing
* PostgreSQL persistence
* Prometheus observability
* Kubernetes orchestration
* autoscaling
* retry systems
* dead letter queue architecture
* structured logging
* failure injection testing
* production-grade rollout safety

---

## Final System Architecture

```
                    ┌────────────────────┐
                    │      Client        │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │      Gateway       │
                    │   FastAPI Service  │
                    └─────────┬──────────┘
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
       ┌───────────────┐             ┌──────────────┐
       │ PostgreSQL DB │             │ Redis Queue  │
       └───────────────┘             └──────┬───────┘
                                            │
                                            ▼
                                  ┌────────────────┐
                                  │     Worker     │
                                  │ Async Consumer │
                                  └────────┬───────┘
                                           │
                                           ▼
                                External Webhook Endpoint
```
---

## Core Technology Stack

| Layer | Technology | 
| --- | --- |
| API framework | FastAPI |
| Runtime | Python 3.11 |
| Database | PostgreSQL |
| Queue | Redis | 
| ORM | SqlAlchemy |
| Containerization | Docker |
| Orchestration | Kubernetes |
| Metrics | Prometheus + Grafana | 
| Load Testing | k6 |
| CI/CD | GitHub Actions |
| Registry | GitHub Container Registry |
| Infrastructure | Docker Compose + Kubernetes |

---

## Final Feature Set 

### API Features
* webhook registration
* event publishing
* event persistence 
* async event processing
* webhook delivery tracking

### Reliability Features
* Redis queue buffering
* retry delivery logic
* dead letter queue
* graceful shutdown
* rolling deployments
* autoscaling
* health probes
* deployment safety guarantees

### Observability Features
* Prometheus metrics
* request latency histograms
* queue delay measurement
* end-to-end latency tracking
* structured JSON logging
* request correltation IDs
* delivery success/failure metrics

### Infrastructure DFeatures
* Dockerized Runtime
* Kubernetes deployments
* ConfigMaps
* Secrets
* PersistentVolumeClaims
* GHCR Image deployments
* Horizontal Pod Autoscaler
* PodDisruptionBudgets

---

## Final Measured System Performance
On distributed load testing using k6:

### Gateway Performace Results

#### Sustained Load Test
| Metric | Result |
| ---- | ---- |
| Virtual users | 50 |
| Total requests | 8179 |
| Throughput | 135 req/sec |
| Failed requests | 0% |
| Average Latency | 368ms |
| Median latency | 318ms |
| p90 latency | 603ms | 
| p95 latency | 704ms |
| Max latency | 2.21s |

### Autoscaling Behavior
* Gateway scaled ```1 pod -> 5 pods ```
* Worker scaled  ```1 pod -> 2 pods```

Kubernetes successfully:
* detected CPU pressure
* created additional replicas
* routed traffic to new pods
* drained old pods during scale-down

### Queue Relaibility Metrics
Measured metrics included:
| Metric | Purpose |
| --- | --- |
| worker_events_processed_total | throughput |
| worker_queue_delay_seconds | queue congestion |
| delivery_success_total | delivery reliability |
| delivery_failure_total | failure visibility |
| end_to_end_latency | total processing latency |

---
## Quantitative Improvements Across Phases

### Redis Queue Introduction
Before Redis queueing:

```
Client request lifecycle:
Client → Gateway → External webhook
```

Problems:

* client blocked on downstream delivery
* webhook latency directly impacted API latency
* failures propagated synchronously
* no buffering under load

Observed behavior:

* long response times
* cascading failures
* synchronous bottlenecks

After Redis queueing:
```
Client → Gateway → Redis queue
                     ↓
                   Worker
                     ↓
               External webhook
```

Effects:

| Improvement	| Result |
| --- | --- |
| Request decoupling |	Gateway returns immediately |
| Load buffering | Redis absorbs bursts |
| Failure isolation |	downstream failures isolated |
| Horizontal scalability |	workers scale independently |
| Throughput increase |	sustained 135 req/sec |

### Observability Improvements
Before Prometheus:
```
No latency visibility
No throughput visibility
No queue visibility
No delivery metrics
```
After instrumentation:

Measured:

* request latency histograms
* queue delays
* delivery latency
* success/failure ratios
* worker throughput
* end-to-end processing latency

Example metrics:
```
gateway_requests_total
histogram_quantile(0.95, rate(gateway_request_latency_seconds_bucket[1m]))
worker_queue_delay_seconds_sum / worker_queue_delay_seconds_count
```

### Kubernetes Reliability Improvements

Before Kubernetes:

* manual container lifecycle
* no self-healing
* no orchestration
* no autoscaling
* no health semantics

After Kubernetes:

| Capability |	Result |
| --- | --- |
| Self-healing |	failed pods recreated automatically |
| Horizontal scaling |	dynamic replica creation |
| Rolling updates |	zero downtime deploys |
| Health management |	readiness/liveness probes |
| Service discovery |	internal networking abstraction |
| Declarative infrastructure |	reproducible environments |

### Failure Handling Improvements

Before retry/DLQ:

* failed deliveries lost permanently
* transient outages caused data loss
* no operational visibility

After retry system:

| Feature |	Result |
| --- | --- |
| Retry scheduling |	transient failures recovered |
| Exponential retry behavior |	controlled retry pressure |
| DLQ storage |	failed events preserved |
| Failure observability |	delivery outcomes measurable |

---
## Final Production Safety Features

### Health Probes
Gateway and Worker each have the following:
* readiness probes
* liveness probes
* startup probes

Effects:
* traffic only routed to healthy pods
* unhealthy containers restarted automatically
* slow startups protected from premature kills

### Graceful Shutdown
Implemented:
```
preStop:
  exec:
    command: ["/bin/sh", "-c", "sleep 10"]
```

Effects:

* in-flight requests completed
* zero-downtime rolling updates
* safer autoscaling termination

### Deployment Safety
Implemented:
```
maxUnavailable: 0
maxSurge: 1
```
Effects:

* rolling deployments without outages
* healthy capacity preserved during deploys

---

## End-to-End Operational Characteristics

| Capability |	Status |
| --- | --- |
| Distributed architecture |	✅ |
| Async event delivery |	✅ |
| Queue buffering |	✅ |
| Retry system |	✅ |
| Dead letter queue |	 ✅ |
| Prometheus monitoring |	✅ |
| Structured logging |	✅ |
| Autoscaling |	✅ |
| Kubernetes orchestration |	✅ |
| Rolling deployments |	✅ |
| Graceful shutdown |	✅ |
| Health probes	| ✅ |
| Failure recovery |	✅ |
| GHCR CI/CD integration |	✅ |
| Persistent storage |	✅ |


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
  * pytest

---

## Setup Instructions

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

# Phase 1 — Initial FastAPI Gateway

## Goal

Build the first webhook ingestion API.

---

## Implemented

* FastAPI application
* PostgreSQL integration
* webhook registration
* event ingestion endpoints
* SQLAlchemy models

---

## Concepts Learned

| Concept            | Description               |
| ------------------ | ------------------------- |
| REST APIs          | HTTP-based service design |
| ORM mapping        | SQLAlchemy models         |
| Persistence        | PostgreSQL integration    |
| Request validation | FastAPI/Pydantic          |

---

# Phase 2 — Database Persistence

## Goal

Persist webhook registrations and event state.

---

## Implemented

* PostgreSQL schema
* migrations
* event persistence
* delivery tracking models

---

## Concepts Learned

| Concept               | Description            |
| --------------------- | ---------------------- |
| relational modeling   | normalized schemas     |
| migrations            | schema evolution       |
| transactions          | consistency guarantees |
| persistence lifecycle | event durability       |

---

# Phase 3 — Worker System + Redis Queue

## Goal

Move webhook delivery out of the request path.

---

## Implemented

* Redis queue
* worker service
* async delivery pipeline
* BRPOP consumption loop

---

## Architectural Shift

Before:

```text
Gateway directly delivers webhook
```

After:

```text
Gateway publishes event → worker consumes asynchronously
```

---

## Concepts Learned

| Concept                        | Description                |
| ------------------------------ | -------------------------- |
| asynchronous systems           | decoupled processing       |
| queues                         | buffering and backpressure |
| producer-consumer architecture | distributed workloads      |
| event-driven systems           | async communication        |

---

# Phase 4 — Dockerization

## Goal

Containerize the entire platform.

---

## Implemented

* Dockerfiles
* Docker Compose
* container networking
* environment injection

---

## Concepts Learned

| Concept               | Description                   |
| --------------------- | ----------------------------- |
| containerization      | isolated runtime environments |
| image layering        | reproducible builds           |
| service networking    | internal DNS                  |
| runtime orchestration | Compose lifecycle             |

---

# Phase 5 — Observability

## Goal

Instrument the system with metrics.

---

## Implemented

* Prometheus metrics
* latency histograms
* throughput counters
* queue delay metrics
* worker processing metrics

---

## Key Metrics

```promql
gateway_requests_total
```

```promql
gateway_request_latency_seconds
```

```promql
worker_events_processed_total
```

---

## Concepts Learned

| Concept                 | Description             |
| ----------------------- | ----------------------- |
| observability           | operational visibility  |
| metrics instrumentation | quantitative monitoring |
| histograms              | latency distributions   |
| SLI measurement         | service performance     |

---

# Phase 6 — CI/CD + GHCR

## Goal

Automate builds and deployments.

---

## Implemented

* GitHub Actions
* automated Docker builds
* GHCR publishing
* SHA-tagged images

---

## Pipeline Flow

```text
Git Push
   ↓
GitHub Actions
   ↓
Tests
   ↓
Docker Build
   ↓
Push to GHCR
```

---

## Concepts Learned

| Concept               | Description                  |
| --------------------- | ---------------------------- |
| CI/CD                 | automated delivery pipelines |
| registry systems      | image distribution           |
| immutable artifacts   | reproducible deployments     |
| deployment automation | infrastructure pipelines     |

---

# Phase 7 — Kubernetes Migration

## Goal

Move the platform to Kubernetes.

---

## Implemented

* Deployments
* Services
* ConfigMaps
* Secrets
* PVCs
* Namespace isolation
* Minikube runtime

---

## Concepts Learned

| Concept                    | Description                      |
| -------------------------- | -------------------------------- |
| orchestration              | distributed container management |
| declarative infrastructure | desired state management         |
| pod lifecycle              | execution semantics              |
| service abstraction        | stable networking                |
| cluster scheduling         | runtime coordination             |

---

# Phase 8 — Autoscaling + Load Testing

## Goal

Validate scaling behavior under load.

---

## Implemented

* HorizontalPodAutoscaler
* CPU-based scaling
* k6 load testing
* throughput benchmarking

---

## Measured Results

| Metric          | Result      |
| --------------- | ----------- |
| Throughput      | 135 req/sec |
| Total requests  | 8,179       |
| Failed requests | 0%          |
| Gateway scaling | 1 → 5 pods  |
| Worker scaling  | 1 → 2 pods  |

---

## Concepts Learned

| Concept                | Description                 |
| ---------------------- | --------------------------- |
| autoscaling            | dynamic resource allocation |
| load testing           | performance validation      |
| resource scheduling    | CPU-based orchestration     |
| distributed elasticity | runtime scaling             |

---

# Phase 9 — Failure Injection + Resilience

## Goal

Force real distributed-system failures.

---

## Injected Failures

| Failure                 | Result                      |
| ----------------------- | --------------------------- |
| pod deletion            | Kubernetes self-healed      |
| Redis outage            | queue stalled safely        |
| PostgreSQL outage       | services failed predictably |
| slow downstream webhook | queue delays increased      |
| delivery failures       | retries triggered           |
| retry exhaustion        | DLQ captured failures       |

---

## Implemented

* retry system
* dead letter queue
* structured logging
* failure observability
* queue pressure validation

---

## Concepts Learned

| Concept                | Description                      |
| ---------------------- | -------------------------------- |
| cascading failures     | distributed instability          |
| retry storms           | uncontrolled retry amplification |
| resilience engineering | recovery-oriented design         |
| failure domains        | system isolation                 |
| operational recovery   | fault handling                   |

---

# Phase 10 — Production Readiness

## Goal

Make the platform operationally safe.

---

## Implemented

* readiness probes
* liveness probes
* startup probes
* rolling deployments
* graceful shutdown
* PodDisruptionBudgets
* resource requests/limits

---

## Concepts Learned

| Concept                  | Description                 |
| ------------------------ | --------------------------- |
| health semantics         | service availability gating |
| zero downtime deploys    | safe rollout mechanics      |
| graceful draining        | connection safety           |
| deployment orchestration | production operations       |
| operational stability    | reliability guarantees      |

---

# Final Engineering Outcome

The project evolved from:

```text
Single FastAPI application
```

into:

```text
Observable, autoscaling, resilient distributed webhook platform
```

The final system demonstrates practical understanding of:

* backend engineering
* distributed systems
* infrastructure orchestration
* DevOps
* observability
* resilience engineering
* production operations
* Kubernetes platform architecture
* cloud-native systems design

---

---

# Final Status

## Completed

✅ Async webhook architecture

✅ Redis queue buffering

✅ PostgreSQL persistence

✅ Metrics instrumentation

✅ Prometheus observability

✅ Dockerized runtime

✅ Kubernetes orchestration

✅ GHCR CI/CD pipelines

✅ Horizontal autoscaling

✅ Failure injection testing

✅ Retry system

✅ Dead letter queue

✅ Structured logging

✅ Graceful shutdown

✅ Zero-downtime deployments

✅ Health probes

✅ Production rollout safety

---

# Future Extensions

Potential next evolutions:

* Grafana dashboards
* distributed tracing
* OpenTelemetry
* Kafka migration
* RabbitMQ support
* multi-region delivery
* webhook signing
* JWT authentication
* rate limiting
* circuit breakers
* Helm charts
* Terraform infrastructure
* cloud-managed Kubernetes
* service mesh integration
* canary deployments
* SLO/SLA management


