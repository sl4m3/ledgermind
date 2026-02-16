import time
import logging
from functools import wraps
from opentelemetry import trace
from prometheus_client import Summary, Counter, Gauge, Histogram

# Prometheus Metrics
LATENCY = Histogram('agent_memory_operation_latency_seconds', 'Latency of memory operations', ['operation'])
DECISIONS_TOTAL = Gauge('agent_memory_decisions_total', 'Total count of decisions', ['status', 'kind'])
GIT_COMMIT_SIZE = Histogram('agent_memory_git_commit_bytes', 'Size of git commits in bytes')
SEARCH_QUALITY = Gauge('agent_memory_search_score_avg', 'Average score of search results')
CONFLICTS_DETECTED = Counter('agent_memory_conflicts_total', 'Total number of conflicts detected')

logger = logging.getLogger("agent-memory-core.telemetry")
tracer = trace.get_tracer("agent-memory-core")

def trace_and_time(operation_name):
    """Decorator to trace and measure latency of a function."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(operation_name):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration = time.time() - start_time
                    LATENCY.labels(operation=operation_name).observe(duration)
        return wrapper
    return decorator

def update_decision_metrics(meta_store):
    """Updates gauges with latest stats from the meta store."""
    try:
        all_decisions = meta_store.list_all()
        # Reset counters or update gauges
        stats = {}
        for d in all_decisions:
            key = (d.get('status', 'unknown'), d.get('kind', 'unknown'))
            stats[key] = stats.get(key, 0) + 1
        
        for (status, kind), count in stats.items():
            DECISIONS_TOTAL.labels(status=status, kind=kind).set(count)
    except Exception as e:
        logger.error(f"Failed to update metrics: {e}")
