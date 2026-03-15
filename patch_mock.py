import re
import numpy as np

def mock_encode(text, **kwargs):
    def get_vec(t):
        v = np.zeros(384)
        words = re.findall(r'\w+', t.lower())
        for w in words:
            v[hash(w) % 384] += 1.0
        norm = np.linalg.norm(v)
        if norm > 0:
            return v / norm
        return v

    if isinstance(text, list):
        return np.array([get_vec(t) for t in text])
    return get_vec(text)
