import os
import subprocess
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from manager import MemoryMultiManager

class EnvironmentContext:
    """
    Инструмент для сбора контекста окружения (файлы, переменные, состояние git).
    Результаты сохраняются в эпизодическую память.
    """
    def __init__(self, manager: 'MemoryMultiManager'):
        self.manager = manager

    def capture_context(self, label: str = "general_context") -> Dict[str, Any]:
        """
        Собирает снимок текущего окружения и записывает его в эпизодическую память.
        """
        context_data = {
            "cwd": os.getcwd(),
            "files": self._get_file_tree(),
            "git_status": self._get_git_status(),
            "env_vars": self._get_filtered_env()
        }

        if self.manager.core:
            # Записываем как эпизодическое событие
            self.manager.core.process_event(
                source="system",
                kind="context_snapshot",
                content=f"Snapshot: {label}",
                context=context_data
            )
            return {"status": "success", "label": label, "message": "Context captured to episodic memory"}
        
        return {"status": "error", "message": "Core memory not initialized"}

    def _get_file_tree(self, max_depth: int = 2) -> List[str]:
        """Возвращает список файлов в текущей директории."""
        try:
            # Используем find или просто os.walk для кроссплатформенности
            files = []
            for root, dirs, filenames in os.walk(".", topdown=True):
                depth = root.count(os.sep)
                if depth >= max_depth:
                    continue
                for f in filenames:
                    files.append(os.path.join(root, f))
                if len(files) > 50: # Лимит для предотвращения переполнения контекста
                    break
            return files
        except Exception:
            return []

    def _get_git_status(self) -> str:
        """Возвращает краткий статус git."""
        try:
            res = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5)
            return res.stdout.strip()
        except Exception:
            return "not a git repo or git not found"

    def _get_filtered_env(self) -> Dict[str, str]:
        """Возвращает безопасные переменные окружения."""
        allowed = {"PYTHONPATH", "LANG", "SHELL", "PWD"}
        return {k: v for k, v in os.environ.items() if k in allowed}
