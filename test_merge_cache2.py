def mock_get_batch_by_fids(fids):
    return [{"fid": fid, "status": "active", "merge_status": "ready", "enrichment_status": "completed"} for fid in fids]

def mock_get_by_fid(fid):
    # Simulate an external call
    return {"fid": fid, "status": "active", "merge_status": "ready", "enrichment_status": "completed"}

def current(search_results):
    for res in search_results:
        target_fid = res["id"]
        actual_target = mock_get_by_fid(target_fid)

def optimized(search_results):
    fids = [res["id"] for res in search_results]
    batch_res = mock_get_batch_by_fids(fids)
    actual_targets = {m["fid"]: m for m in batch_res}
    for res in search_results:
        target_fid = res["id"]
        actual_target = actual_targets.get(target_fid)

search_results = [{"id": f"fid_{i}"} for i in range(30)]

import timeit
print("Current:", timeit.timeit(lambda: current(search_results), number=100000))
print("Optimized (Batch):", timeit.timeit(lambda: optimized(search_results), number=100000))
