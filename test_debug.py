import os
import shutil
import concurrent.futures
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.exceptions import ConflictError, InvariantViolation
from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation

def test():
    storage = "debug_mem"
    if os.path.exists(storage):
        shutil.rmtree(storage)
    os.makedirs(storage)

    target = "shared_resource"

    def worker(i):
        worker_mem = None
        try:
            print(f"Worker {i} starting")
            worker_mem = Memory(storage_path=storage)
            print(f"Worker {i} memory init done")
            worker_mem.record_decision(f"Title {i}", target, f"Rationale {i}")
            print(f"Worker {i} success")
            return "success"
        except (ConflictError, InvariantViolation, IntegrityViolation) as e:
            print(f"Worker {i} conflict: {e}")
            return "conflict"
        except Exception as e:
            print(f"Worker {i} error: {e}")
            return f"error: {e}"
        finally:
            if worker_mem:
                worker_mem.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, 0)
        f2 = executor.submit(worker, 1)
        res = [f1.result(), f2.result()]

    print(res)

test()
