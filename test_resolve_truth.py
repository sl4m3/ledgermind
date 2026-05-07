def mock_get_by_fid(fid):
    # Simulate DB lookup
    return {"fid": fid, "superseded_by": None if fid == "fid_2" else f"fid_{int(fid.split('_')[1]) + 1}", "status": "active" if fid == "fid_2" else "superseded"}

def current_resolve(fid, depth=0):
    if depth >= 20:
        return None
    meta = mock_get_by_fid(fid)
    if not meta:
        return None
    next_fid = meta.get("superseded_by")
    if meta.get("status") == "active" or not next_fid:
        return meta
    truth = current_resolve(next_fid, depth + 1)
    if truth is None:
        if depth > 0 and depth >= 19:
            return None
        return meta
    return truth

def optimized_resolve(fid):
    # iterative
    current_fid = fid
    for depth in range(20):
        meta = mock_get_by_fid(current_fid)
        if not meta:
            return None
        next_fid = meta.get("superseded_by")
        if meta.get("status") == "active" or not next_fid:
            return meta
        current_fid = next_fid
    return None

import timeit
print("Current:", timeit.timeit(lambda: current_resolve("fid_0"), number=100000))
print("Optimized:", timeit.timeit(lambda: optimized_resolve("fid_0"), number=100000))
