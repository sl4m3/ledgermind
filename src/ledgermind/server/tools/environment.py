import os
import subprocess
from typing import Dict, Any, List, Optional
from ledgermind.core.api.memory import Memory

class EnvironmentContext:
    """
    Инструмент для сбора контекста окружения (файлы, переменные, состояние git).
    Результаты сохраняются в эпизодическую память через ядро.
    """
    def __init__(self, memory: Memory):
        self.memory = memory

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

        # Записываем как эпизодическое событие напрямую через ядро
        self.memory.process_event(
            source="system",
            kind="context_snapshot",
            content=f"Snapshot: {label}",
            context=context_data
        )
        return {"status": "success", "label": label, "message": "Context captured to episodic memory"}

    def _get_file_tree(self, max_depth: int = 2) -> List[str]:
        try:
            files = []
            for root, dirs, filenames in os.walk(".", topdown=True):
                depth = root.count(os.sep)
                if depth >= max_depth:
                    continue
                for f in filenames:
                    files.append(os.path.join(root, f))
                if len(files) > 50:
                    break
            return files
        except Exception:
            return []

    def _get_git_status(self) -> str:
        try:
            res = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5)
            return res.stdout.strip()
        except Exception:
            return "not a git repo or git not found"

    def _get_filtered_env(self) -> Dict[str, str]:
        allowed = {"PYTHONPATH", "LANG", "SHELL", "PWD"}
        return {k: v for k, v in os.environ.items() if k in allowed}
