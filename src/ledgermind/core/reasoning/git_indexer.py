import subprocess
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from ledgermind.core.core.schemas import MemoryEvent

class GitIndexer:
    """
    Модуль для индексации истории Git и превращения коммитов в события памяти.
    Это позволяет ReflectionEngine учитывать изменения кода, сделанные людьми.
    """
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self._validate_path_safety()

    def _validate_path_safety(self):
        # Security: Prevent path traversal and access to unauthorized directories
        # Resolve the absolute path of the target repo
        abs_repo_path = os.path.realpath(os.path.abspath(self.repo_path))

        # Resolve the current working directory
        # We assume the agent is running in the root of the project it is allowed to access
        cwd = os.path.realpath(os.getcwd())

        # Check if the repo path is within the CWD
        try:
            if os.path.commonpath([cwd, abs_repo_path]) != cwd:
                raise ValueError(f"Security violation: Access to {self.repo_path} is outside the allowed scope (CWD: {cwd}).")
        except ValueError:
            # Can happen if paths are on different drives on Windows
            raise ValueError(f"Security violation: Access to {self.repo_path} is outside the allowed scope.")

    def get_recent_commits(self, limit: int = 10, since_hash: Optional[str] = None) -> List[Dict[str, Any]]:
        """Извлекает историю коммитов через git log."""
        try:
            # Формат: hash|author|date|subject|body
            # Используем --reverse чтобы идти от старых к новым при индексации
            format_str = "%H|%an|%ai|%s|%b%x00"
            cmd = ["git", "log", f"-n {limit}", f"--format={format_str}"]
            
            if since_hash:
                # Security: Validate hash to prevent argument injection
                import re
                if not re.match(r'^[a-f0-9]{4,40}$', since_hash):
                    logger.warning(f"Invalid since_hash detected: {since_hash}. Ignoring.")
                else:
                    cmd.append(f"{since_hash}..HEAD")
            
            res = subprocess.run(cmd, cwd=self.repo_path, capture_output=True, text=True, check=True) # nosec B603 B607
            if not res.stdout.strip():
                return []

            commits = []
            # Разделяем по нулевому байту, который мы добавили в конец каждого коммита
            for raw_commit in res.stdout.split('\x00'):
                if not raw_commit.strip():
                    continue
                
                parts = raw_commit.strip().split('|', 4)
                if len(parts) < 4:
                    continue
                
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "subject": parts[3],
                    "body": parts[4] if len(parts) > 4 else ""
                })
            
            return commits
        except Exception as e:
            # Не является git репозиторием или git не установлен
            return []

    def index_to_memory(self, memory_instance, limit: int = 20) -> int:
        """Сканирует Git и записывает новые коммиты в эпизодическую память."""
        # 1. Пытаемся найти хэш последнего проиндексированного коммита
        # Сначала проверяем в надежном хранилище метаданных
        last_hash = memory_instance.semantic.meta.get_config('last_indexed_commit_hash')
        
        # Fallback к поиску в последних событиях если в конфиге пусто
        if not last_hash:
            recent_events = memory_instance.episodic.query(limit=50)
            for ev in recent_events:
                if ev.get('kind') == 'commit_change':
                    last_hash = ev.get('context', {}).get('hash')
                    break
        
        # 2. Получаем новые коммиты
        new_commits = self.get_recent_commits(limit=limit, since_hash=last_hash)
        
        if not new_commits:
            return 0

        indexed_count = 0
        latest_hash = last_hash
        
        for commit in reversed(new_commits): # От старых к новым
            # Дополнительно получаем список измененных файлов для контекста
            try:
                diff_res = subprocess.run(
                    ["git", "show", "--name-only", "--format=", commit['hash']], 
                    cwd=self.repo_path, capture_output=True, text=True
                ) # nosec B603 B607
                changed_files = [f for f in diff_res.stdout.strip().split('\n') if f]
                
                # Heuristic: Infer target from common path prefix or first file
                # If file is src/module/file.py, target is 'module'
                inferred_target = None
                if changed_files:
                    first_file = changed_files[0]
                    parts = first_file.split('/')
                    if len(parts) > 1:
                        if parts[0] in ['src', 'lib', 'app']: inferred_target = parts[1]
                        else: inferred_target = parts[0]
            except Exception:
                changed_files = []
                inferred_target = None

            date_str = commit['date'].strip()
            # Handle ISO 8601 with colon in timezone (Python < 3.11 compatibility)
            # e.g. 2026-02-21 01:23:28 +03:00 -> 2026-02-21 01:23:28 +0300
            if len(date_str) > 6 and date_str[-3] == ':':
                date_str = date_str[:-3] + date_str[-2:]
            
            event = MemoryEvent(
                source="system",
                kind="commit_change",
                content=f"Commit by {commit['author']}: {commit['subject']}",
                context={
                    "hash": commit['hash'],
                    "author": commit['author'],
                    "full_message": commit['body'],
                    "changed_files": changed_files,
                    "target": inferred_target,
                    "type": "git_history"
                },
                timestamp=datetime.fromisoformat(date_str)
            )
            
            # Deep Duplicate Check
            if not memory_instance.episodic.find_duplicate(event):
                memory_instance.episodic.append(event)
                indexed_count += 1
            
            latest_hash = commit['hash']
            
        # Сохраняем последний проиндексированный хэш
        if latest_hash:
            memory_instance.semantic.meta.set_config('last_indexed_commit_hash', latest_hash)
            
        return indexed_count
