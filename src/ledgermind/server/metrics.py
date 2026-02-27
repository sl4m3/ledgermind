from prometheus_client import Counter, Histogram, Gauge

# Metrics definitions
TOOL_CALLS = Counter("agent_memory_tool_calls_total", "Total number of tool calls", ["tool", "status"])
TOOL_LATENCY = Histogram("agent_memory_tool_latency_seconds", "Latency of tool calls in seconds", ["tool"])

PHASE_TRANSITIONS = Counter('ledgermind_phase_transitions_total', 'Total number of phase transitions', ['from_phase', 'to_phase'])
VITALITY_DISTRIBUTION = Gauge('ledgermind_streams_by_vitality', 'Number of streams in each vitality state', ['vitality'])
PHASE_DISTRIBUTION = Gauge('ledgermind_streams_by_phase', 'Number of streams in each phase', ['phase'])
STREAM_PROMOTIONS = Counter('ledgermind_stream_promotions_total', 'Total number of stream promotions', ['target_phase'])
