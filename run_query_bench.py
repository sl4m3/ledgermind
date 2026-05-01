import time
import math

class MockLoop:
    def process_with_min(self, iterations):
        _log10 = math.log10
        cand = {'base_score': 0.5}
        for i in range(iterations):
            evidence_count = i
            if evidence_count > 0:
                reliability_boost = min(0.2, _log10(evidence_count + 1) * 0.05)
                cand["base_score"] = cand.get("base_score", 0.0) + reliability_boost

            cand["similarity_score"] = min(1.0, cand.get("base_score", 0.0))

    def process_inline(self, iterations):
        _log10 = math.log10
        cand = {'base_score': 0.5}
        for i in range(iterations):
            evidence_count = i
            base = cand.get("base_score", 0.0)
            if evidence_count > 0:
                val1 = _log10(evidence_count + 1) * 0.05
                reliability_boost = 0.2 if val1 > 0.2 else val1
                base += reliability_boost
                cand["base_score"] = base

            cand["similarity_score"] = 1.0 if base > 1.0 else base

m = MockLoop()
start = time.time()
m.process_with_min(2000000)
end = time.time()
print("min():", end - start)

start = time.time()
m.process_inline(2000000)
end = time.time()
print("inline:", end - start)
