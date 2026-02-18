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

    def get_recent_commits(self, limit: int = 10, since_hash: Optional[str] = None) -> List[Dict[str, Any]]:
        """Извлекает историю коммитов через git log."""
        try:
            # Формат: hash|author|date|subject|body
            # Используем --reverse чтобы идти от старых к новым при индексации
            format_str = "%H|%an|%ai|%s|%b%x00"
            cmd = ["git", "log", f"-n {limit}", f"--format={format_str}"]
            
            if since_hash:
                cmd.append(f"{since_hash}..HEAD")
            
            res = subprocess.run(cmd, cwd=self.repo_path, capture_output=True, text=True, check=True)
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
        # Мы ищем его в последних событиях типа commit_change
        recent_events = memory_instance.episodic.query(limit=50)
        last_hash = None
        for ev in recent_events:
            if ev.get('kind') == 'commit_change':
                last_hash = ev.get('context', {}).get('hash')
                break
        
        # 2. Получаем новые коммиты
        new_commits = self.get_recent_commits(limit=limit, since_hash=last_hash)
        
        indexed_count = 0
        for commit in reversed(new_commits): # От старых к новым
            event = MemoryEvent(
                source="system",
                kind="commit_change",
                content=f"Commit by {commit['author']}: {commit['subject']}",
                context={
                    "hash": commit['hash'],
                    "author": commit['author'],
                    "full_message": commit['body'],
                    "type": "git_history"
                },
                timestamp=datetime.fromisoformat(commit['date'].strip())
            )
            memory_instance.episodic.append(event)
            indexed_count += 1
            
        return indexed_count
