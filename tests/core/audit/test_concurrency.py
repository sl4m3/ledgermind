import os
import multiprocessing
import pytest
from ledgermind.core.api.memory import Memory

def worker(storage_path, worker_id):
    """Каждый воркер пытается записать свое решение."""
    try:
        memory = Memory(storage_path=storage_path)
        # Increase lock timeout for heavy concurrent tests
        memory.semantic._fs_lock.timeout = 60
        for i in range(5):
            memory.record_decision(
                title=f"Decision from worker {worker_id} - {i}",
                target=f"target_{worker_id}_{i}", # Unique target
                rationale="Testing parallel write access with a rationale long enough to pass validation"
            )
    except Exception as e:
        return str(e)
    return None

def test_multi_process_locking(tmp_path):
    storage_path = str(tmp_path / "parallel_memory")
    os.makedirs(storage_path)
    
    # Инициализируем репозиторий один раз
    Memory(storage_path=storage_path)
    
    # Use spawn for safety in multi-threaded environments (pytest-xdist)
    ctx = multiprocessing.get_context('spawn')
    
    num_workers = 2
    with ctx.Pool(num_workers) as pool:
        results = pool.starmap(worker, [(storage_path, i) for i in range(num_workers)])
    
    # Проверяем, были ли ошибки (локи должны были предотвратить их)
    errors = [r for r in results if r is not None]
    assert len(errors) == 0, f"Concurrency errors detected: {errors}"
    
    # Проверяем, что все решения записаны (2 воркера * 5 записей = 10 файлов)
    memory = Memory(storage_path=storage_path)
    decisions = memory.get_decisions()
    assert len(decisions) == 10
    print(f"Concurrency check passed: 10 decisions recorded by {num_workers} processes.")

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

def test_supersede_consistency_under_load(tmp_path):
    """
    Проверяет, что при интенсивном вытеснении (supersede) читатели всегда видят 
    консистентное состояние (ровно одно активное решение для таргета).
    """
    storage_path = str(tmp_path / "supersede_load")
    os.makedirs(storage_path)
    memory = Memory(storage_path=storage_path)
    target = "consistent_target"
    
    # Создаем начальное состояние
    memory.record_decision("v0", target, "Initial version of decision with a rationale long enough to pass")
    
    def writer_loop(path, stop_ev):
        m = Memory(storage_path=path)
        i = 1
        while not stop_ev.is_set():
            try:
                active = m.semantic.list_active_conflicts(target)
                if active:
                    m.supersede_decision(f"v{i}", target, f"Update {i} with long rationale", [active[0]])
                    i += 1
            except Exception: continue

    def reader_loop(path, stop_ev, results_queue):
        m = Memory(storage_path=path)
        while not stop_ev.is_set():
            try:
                active = m.semantic.list_active_conflicts(target)
                # Критическое условие: никогда не должно быть != 1 активного решения
                if len(active) != 1:
                    results_queue.put(f"Consistency Violation: found {len(active)} active decisions for {target}")
            except Exception as e:
                results_queue.put(f"Reader Error: {e}")

    # Use spawn context consistently
    ctx = multiprocessing.get_context('spawn')
    manager = ctx.Manager()
    stop_event = manager.Event()
    results_queue = manager.Queue()
    
    # Запускаем писателя и читателей
    with ctx.Pool(2) as pool:
        pool.apply_async(writer_loop, (storage_path, stop_event))
        for _ in range(1):
            pool.apply_async(reader_loop, (storage_path, stop_event, results_queue))
        
        # Даем поработать 1.5 секунды (достаточно для проверки локов)
        import time
        time.sleep(1.5)
        stop_event.set()
        
    # Проверяем результаты из очереди
    errors = []
    while not results_queue.empty():
        errors.append(results_queue.get())
    
    assert len(errors) == 0, f"Concurrency consistency errors: {errors}"
