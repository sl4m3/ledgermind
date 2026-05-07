import timeit

def mock_get_batch_by_fids(fids):
    return [{"fid": fid, "status": "active", "merge_status": "ready", "enrichment_status": "completed"} for fid in fids]

def current(search_results):
    for res in search_results:
        target_fid = res["id"]
        # Simulate getting from dict vs batch loop
        pass

def optimized(search_results, full_meta_map):
    # This simulates what we'd do
    missing_fids = [res["id"] for res in search_results if res["id"] not in full_meta_map]
    if missing_fids:
        batch_res = mock_get_batch_by_fids(missing_fids)
        for m in batch_res:
            full_meta_map[m["fid"]] = m

    for res in search_results:
        target_fid = res["id"]
        actual_target = full_meta_map.get(target_fid)

search_results = [{"id": f"fid_{i}"} for i in range(30)]
full_meta_map = {f"fid_{i}": {"fid": f"fid_{i}", "status": "active", "merge_status": "ready", "enrichment_status": "completed"} for i in range(15)}

print("Optimized (Batch with Cache):", timeit.timeit(lambda: optimized(search_results, full_meta_map.copy()), number=100000))
