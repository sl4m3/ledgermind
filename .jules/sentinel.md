## 2025-02-26 - [Scanner Symlink Traversal]
**Vulnerability:** ProjectScanner followed symlinks, allowing read access to files outside the project root if a malicious symlink was present.
**Learning:** File enumeration tools must explicitly handle or ignore symlinks to prevent unintentional path traversal and information disclosure.
**Prevention:** always check `os.path.islink()` before opening files in scanner/backup tools and skip them unless explicitly required and validated.
