import time
from collections import defaultdict

metrics = {
    "request_count": 0,
    "request_latency": [],
}

def record_request(latency: float):
    metrics["request_count"] += 1
    metrics["request_latency"].append(latency)


def get_metrics():
    latencies = metrics["request_latency"]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    return {
        "request_count": metrics["request_count"],
        "avg_latency": round(avg_latency, 4),
    }
