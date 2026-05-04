from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    'gateway_requests_total',
    'Total number of API requests'
)

REQUEST_LATENCY = Histogram(
    'gateway_request_latency_seconds',
    'Request latency in seconds'
)