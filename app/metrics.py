from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    'gateway_requests_total',
    'Total number of API requests'
)

REQUEST_LATENCY = Histogram(
    'gateway_request_latency_seconds',
    'Request latency in seconds'
)

RETRY_ATTEMPTS = Counter(
    "worker_retry_attempts_total",
    "Total retry attempts"
)

DLQ_EVENTS = Counter(
    "worker_dlq_events_total",
    "Events moved to dead letter queue"
)