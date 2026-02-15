import os
import multiprocessing
import pytest
from agent_memory_core.api.memory import Memory

def worker(storage_path, worker_id):
    """Каждый воркер пытается записать свое решение."""
    try:
        memory = Memory(storage_path=storage_path)
        for i in range(5):
            memory.record_decision(
                title=f"Decision from worker {worker_id} - {i}",
                target=f"target_{worker_id}_{i}", # Unique target
                rationale="Testing parallel write access"
            )
    except Exception as e:
        return str(e)
    return None

def test_multi_process_locking(tmp_path):
    storage_path = str(tmp_path / "parallel_memory")
    os.makedirs(storage_path)
    
    # Инициализируем репозиторий один раз
    Memory(storage_path=storage_path)
    
    num_workers = 5
    with multiprocessing.Pool(num_workers) as pool:
        results = pool.starmap(worker, [(storage_path, i) for i in range(num_workers)])
    
    # Проверяем, были ли ошибки (локи должны были предотвратить их)
    errors = [r for r in results if r is not None]
    assert len(errors) == 0, f"Concurrency errors detected: {errors}"
    
    # Проверяем, что все решения записаны (5 воркеров * 5 записей = 25 файлов)
    memory = Memory(storage_path=storage_path)
    decisions = memory.get_decisions()
    assert len(decisions) == 25
    print(f"Concurrency check passed: 25 decisions recorded by {num_workers} processes.")

def reader_worker(storage_path, stop_event):
    """Читатель постоянно опрашивает память, пока не получит сигнал остановки."""
    try:
        memory = Memory(storage_path=storage_path)
        while not stop_event.is_set():
            decisions = memory.get_decisions()
            # Проверяем базовую целостность: каждое решение должно существовать
            for d in decisions:
                file_path = os.path.join(storage_path, "semantic", d)
                assert os.path.exists(file_path), f"Reader saw non-existent file: {d}"
    except Exception as e:
        return str(e)
    return None

def test_read_while_write_consistency(tmp_path):
    storage_path = str(tmp_path / "rw_consistency")
    os.makedirs(storage_path)
    Memory(storage_path=storage_path)
    
    manager = multiprocessing.Manager()
    stop_event = manager.Event()
    
    num_readers = 3
    with multiprocessing.Pool(num_readers + 1) as pool:
        # Запускаем читателей
        reader_results = [pool.apply_async(reader_worker, (storage_path, stop_event)) for _ in range(num_readers)]
        
        # Запускаем писателя (те же 10 записей)
        writer_err = worker(storage_path, 999)
        
        # Останавливаем читателей
        stop_event.set()
        
        assert writer_err is None
        for r in reader_results:
            assert r.get() is None, f"Reader error: {r.get()}"
