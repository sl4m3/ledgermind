import sys

def mock_get_by_fid(fid):
    return {"fid": fid, "status": "active", "merge_status": "ready", "enrichment_status": "completed"}

def current(search_results):
    for res in search_results:
        target_fid = res["id"]
        actual_target = mock_get_by_fid(target_fid)

def optimized(search_results):
    cache = {res["id"]: mock_get_by_fid(res["id"]) for res in search_results}
    for res in search_results:
        target_fid = res["id"]
        actual_target = cache.get(target_fid)

search_results = [{"id": f"fid_{i}"} for i in range(30)]

import timeit
print("Current:", timeit.timeit(lambda: current(search_results), number=100000))
print("Optimized:", timeit.timeit(lambda: optimized(search_results), number=100000))
