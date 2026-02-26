from prometheus_client import Counter, Histogram

# Metrics definitions
TOOL_CALLS = Counter("agent_memory_tool_calls_total", "Total number of tool calls", ["tool", "status"])
TOOL_LATENCY = Histogram("agent_memory_tool_latency_seconds", "Latency of tool calls in seconds", ["tool"])
