import os
from pathlib import Path
from typing import List, Dict

class ProjectScanner:
    """
    Сканирует структуру проекта и ключевые файлы для инициализации базовых знаний в памяти агента.
    """
    def __init__(self, root_path: str = "."):
        cwd = Path.cwd().resolve()
        target_path = (cwd / root_path).resolve()

        if not target_path.is_relative_to(cwd):
             raise ValueError(f"Access denied: path '{root_path}' traverses outside the current working directory.")

        self.root_path = str(target_path)
        self.ignore_dirs = {
            ".git", "node_modules", "venv", ".venv", "__pycache__", 
            ".pytest_cache", "ledgermind", "build", "dist", ".idea", ".vscode", "target"
        }
        self.target_files = {
            "README.md", "ARCHITECTURE.md", "pyproject.toml", "package.json", 
            "requirements.txt", "Cargo.toml", "go.mod", "Makefile", "docker-compose.yml",
            "setup.py", "tox.ini", "pytest.ini", ".env.example", "LICENSE", "CONTRIBUTING.md",
            "API_REFERENCE.md", "CONFIGURATION.md", "INTEGRATION_GUIDE.md"
        }
        self.max_file_size = 64 * 1024  # 64 KB limit
        self.max_depth = 7

    def scan(self) -> str:
        """
        Выполняет сканирование и возвращает структурированный текстовый отчет.
        """
        tree = self._get_tree()
        files_content = self._get_files_content()
        
        result = [
            "# Project Context Scan",
            "This is an automated scan of the project structure and key configuration files.",
            "",
            "### ⚠️ IMPORTANT: MEMORY STORAGE POLICY",
            "When recording decisions using `record_decision`, ALWAYS follow these rules:",
            "1. **Use flat structure**: Set `namespace='default'` (or omit it) for all general project knowledge.",
            "   DO NOT create namespaces like 'architecture' or 'dependencies' unless physical isolation is required.",
            "2. **Categorization**: Use the `title` and `target` fields for semantic grouping.",
            "   Example: `record_decision(title='Project Architecture', target='core', ...)`",
            "3. **Atomic Records**: Create MULTIPLE separate records instead of one giant file.",
            "",
            "## 1. Directory Structure",
            "```text",
            tree,
            "```",
            "",
            "## 2. Key Files",
        ]
        
        if files_content:
            for file_path, content in files_content.items():
                result.append(f"### {file_path}")
                result.append("```")
                result.append(content)
                result.append("```")
                result.append("")
        else:
            result.append("No standard key files found.")
            
        return "\\n".join(result).replace("\\n", "\n")

    def _get_tree(self) -> str:
        tree_lines = []
        try:
            for root, dirs, files in os.walk(self.root_path, topdown=True):
                # Filter out ignored directories
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
                
                rel_path = os.path.relpath(root, self.root_path)
                depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
                
                if depth > self.max_depth:
                    dirs[:] = []  # Stop traversing deeper
                    continue
                
                indent = "  " * depth
                if rel_path != '.':
                    tree_lines.append(f"{indent}- {os.path.basename(root)}/")
                else:
                    tree_lines.append("- ./")
                
                for f in files:
                    # Ignore compiled and hidden files
                    if f.endswith('.pyc') or f.endswith('.pyo') or f.startswith('.'):
                        continue
                    tree_lines.append(f"{indent}  - {f}")
                    
                # Limit overall size of the tree to prevent excessive output
                if len(tree_lines) > 1000:
                    tree_lines.append(f"{indent}  ... [Tree truncated, exceeded 1000 entries] ...")
                    dirs[:] = []
                    break
                    
            if not tree_lines:
                return "Empty or inaccessible directory."
                
            return "\n".join(tree_lines)
        except Exception as e:
            return f"Error reading directory structure: {e}"

    def _get_files_content(self) -> Dict[str, str]:
        contents = {}
        try:
            for root, dirs, files in os.walk(self.root_path, topdown=True):
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
                
                rel_path = os.path.relpath(root, self.root_path)
                
                for f in files:
                    # Match target files or any .md file (documentation)
                    if f in self.target_files or f.lower().endswith('.md'):
                        file_path = os.path.join(root, f)

                        # Security: Do not follow symlinks to avoid path traversal
                        if os.path.islink(file_path):
                            continue

                        rel_file_path = os.path.relpath(file_path, self.root_path)
                        
                        try:
                            if os.path.getsize(file_path) > self.max_file_size:
                                contents[rel_file_path] = f"[File skipped: Exceeds size limit of {self.max_file_size} bytes]"
                                continue
                                
                            with open(file_path, 'r', encoding='utf-8') as f_in:
                                content = f_in.read()
                                if len(content) > 6000:
                                    content = content[:6000] + "\n...[Truncated due to length]..."
                                contents[rel_file_path] = content
                        except Exception as e:
                            contents[rel_file_path] = f"[Error reading file: {e}]"
        except Exception as e:
             pass
        return contents
