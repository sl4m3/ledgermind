## 2024-05-24 - Missing Event Listener Cleanup (Memory Leak / DoS)
**Vulnerability:** FastApi SSE and WebSocket endpoints (`gateway.py`) did not unsubscribe the `on_change` event listeners from `EventEmitter` when clients disconnected. Over time, each connection leaked an event listener, consuming memory and causing excessive callbacks, resulting in a Denial of Service (DoS) vulnerability via resource exhaustion.
**Learning:** `EventEmitter` pattern in this architecture lacked an explicit `unsubscribe()` capability, making it impossible to manage listener lifecycles. Also, endpoints need `try...finally` blocks around the async generators and loops.
**Prevention:** Ensure that any event listener registered inside an endpoint explicitly implements a `try...finally` teardown using a corresponding `unsubscribe()` method to cleanly close out the connection state.

## 2024-05-25 - API Key Timing Attack Vulnerability
**Vulnerability:** API key verification in `gateway.py` and `server.py` used regular string equality operators (`==` or `!=`). Regular string comparisons check characters sequentially and return early if there's a mismatch. The time it takes for the comparison to return can reveal how many characters match, enabling attackers to systematically brute-force the API key through a timing attack.
**Learning:** Python's standard string comparison must never be used to compare secrets (passwords, tokens, API keys).
**Prevention:** Always use `hmac.compare_digest()` to compare security tokens or credentials, as it performs the comparison in constant time, regardless of how much of the string matches.
