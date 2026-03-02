import os
import time
import threading
from ledgermind.core.api.memory import Memory
from ledgermind.server.background import BackgroundWorker

def test_worker_locking(tmp_path):
    storage = str(tmp_path / "memory")
    os.makedirs(storage, exist_ok=True)
    memory = Memory(storage_path=storage)
    
    worker1 = BackgroundWorker(memory)
    worker2 = BackgroundWorker(memory)
    
    print("Starting worker 1...")
    worker1.start()
    assert worker1.status == "running"
    assert os.path.exists(os.path.join(storage, "worker.pid"))
    
    print("Starting worker 2 (should be busy)...")
    worker2.start()
    assert worker2.status == "busy"
    assert worker2.maintenance_thread is None
    
    print("Stopping worker 1...")
    worker1.stop()
    assert worker1.status == "stopped"
    assert not os.path.exists(os.path.join(storage, "worker.pid"))
    
    print("Starting worker 2 (should now run)...")
    worker2.start()
    assert worker2.status == "running"
    worker2.stop()
    print("Test passed!")

if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        test_worker_locking(Path(tmp))
