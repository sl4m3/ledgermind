import threading
import time
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger("ledgermind.worker.coordinator")

class WorkerCoordinator:
    """
    Координирует доступ воркеров к общим ресурсам.
    
    Правила:
    1. Enrichment и Reflection не могут работать одновременно
    2. Enrichment имеет приоритет (чаще запускается, короче циклы)
    3. Reflection ждет завершения Enrichment
    
    Механизм:
    - Используем RLock для потокобезопасности
    - Conditions для ожидания событий
    - Context managers для автоматического освобождения
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # Флаги активности
        self._enrichment_active = False
        self._reflection_active = False
        
        # Conditions для ожидания
        self._enrichment_done = threading.Condition(self._lock)
        self._reflection_done = threading.Condition(self._lock)
        
        # Статистика
        self._enrichment_count = 0
        self._enrichment_completed = 0
        self._reflection_count = 0
        self._reflection_completed = 0
        self._reflection_skipped = 0
        self._reflection_wait_total = 0.0
    
    @property
    def enrichment_active(self) -> bool:
        """Проверить активен ли Enrichment."""
        with self._lock:
            return self._enrichment_active
    
    @property
    def reflection_active(self) -> bool:
        """Проверить активен ли Reflection."""
        with self._lock:
            return self._reflection_active
    
    @property
    def stats(self) -> dict:
        """Вернуть статистику работы координатора."""
        with self._lock:
            return {
                "enrichment_active": self._enrichment_active,
                "reflection_active": self._reflection_active,
                "enrichment_started": self._enrichment_count,
                "enrichment_completed": self._enrichment_completed,
                "reflection_started": self._reflection_count,
                "reflection_completed": self._reflection_completed,
                "reflection_skipped": self._reflection_skipped,
                "reflection_wait_total_sec": round(self._reflection_wait_total, 2),
            }
    
    @contextmanager
    def enrichment_context(self, timeout: Optional[float] = None):
        """
        Контекст для EnrichmentWorker.
        
        Блокирует запуск Reflection пока enrichment активен.
        Enrichment всегда запускается сразу (приоритетный).
        
        timeout: Максимальное время выполнения (None = без лимита)
        """
        start_time = time.time()
        
        with self._lock:
            self._enrichment_active = True
            self._enrichment_count += 1
            logger.info(f"Enrichment started (active={self._enrichment_active})")
        
        try:
            yield
        finally:
            with self._lock:
                elapsed = time.time() - start_time
                self._enrichment_active = False
                self._enrichment_completed += 1
                
                # Уведомить Reflection что enrichment завершен
                self._enrichment_done.notify_all()
                
                logger.info(f"Enrichment completed ({elapsed:.1f}s)")
    
    @contextmanager
    def reflection_context(self, timeout: Optional[float] = 300.0, skip_if_busy: bool = True):
        """
        Контекст для ReflectionWorker.
        
        Ждет завершения Enrichment перед запуском.
        
        timeout: Максимальное время ожидания старта (секунды, default=300)
        skip_if_busy: Если True, пропустить цикл если timeout истек
        
        Raises:
            TimeoutError: Если timeout истек и skip_if_busy=False
        """
        start_time = time.time()
        waited = False
        wait_time = 0.0
        
        with self._lock:
            # Ждать пока Enrichment не завершится
            while self._enrichment_active:
                waited = True
                
                # Проверить timeout
                if timeout:
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        self._reflection_skipped += 1
                        if skip_if_busy:
                            logger.warning(
                                f"Reflection skipped: enrichment still active after {elapsed:.1f}s"
                            )
                            # Вернуть контекст который ничего не делает
                            yield
                            return
                        else:
                            raise TimeoutError(
                                f"Reflection timeout after {timeout}s waiting for enrichment"
                            )
                
                # Ждать уведомления от Enrichment
                remaining = None
                if timeout:
                    remaining = max(0.1, timeout - (time.time() - start_time))
                
                logger.debug(f"Reflection waiting for enrichment (timeout={remaining:.1f}s)")
                self._enrichment_done.wait(timeout=remaining or 1.0)
            
            # Enrichment завершен, можно запускать Reflection
            wait_time = time.time() - start_time
            self._reflection_wait_total += wait_time
            self._reflection_active = True
            self._reflection_count += 1
            
            logger.info(
                f"Reflection started (waited={waited}, wait_time={wait_time:.1f}s)"
            )
        
        try:
            yield
        finally:
            with self._lock:
                self._reflection_active = False
                self._reflection_completed += 1
                
                # Уведомить Enrichment что reflection завершен
                self._reflection_done.notify_all()
                
                logger.info(f"Reflection completed")
    
    def can_start_reflection(self) -> bool:
        """
        Проверить можно ли запустить Reflection.
        
        Returns:
            True если Enrichment не активен
        """
        with self._lock:
            return not self._enrichment_active
    
    def can_start_enrichment(self) -> bool:
        """
        Проверить можно ли запустить Enrichment.
        
        Returns:
            True (Enrichment всегда может запуститься)
        """
        return True
    
    def wait_for_idle(self, timeout: Optional[float] = 60.0) -> bool:
        """
        Ждать пока все воркеры завершат работу.
        
        timeout: Максимальное время ожидания (секунды)
        
        Returns:
            True если все воркеры завершены, False если timeout
        """
        start_time = time.time()
        
        with self._lock:
            while self._enrichment_active or self._reflection_active:
                if timeout:
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        logger.warning(
                            f"Wait for idle timeout ({elapsed:.1f}s), "
                            f"enrichment={self._enrichment_active}, "
                            f"reflection={self._reflection_active}"
                        )
                        return False
                
                remaining = None
                if timeout:
                    remaining = max(0.1, timeout - (time.time() - start_time))
                
                self._enrichment_done.wait(timeout=remaining or 1.0)
                self._reflection_done.wait(timeout=0.1)
        
        return True
    
    def force_stop_all(self):
        """
        Принудительно остановить все воркеры.
        
        Используется при shutdown.
        """
        with self._lock:
            was_enrichment = self._enrichment_active
            was_reflection = self._reflection_active
            
            self._enrichment_active = False
            self._reflection_active = False
            
            # Уведомить всех ожидающих
            self._enrichment_done.notify_all()
            self._reflection_done.notify_all()
            
            if was_enrichment or was_reflection:
                logger.warning(
                    f"Force stopped: enrichment={was_enrichment}, reflection={was_reflection}"
                )
