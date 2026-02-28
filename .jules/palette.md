## 2025-03-05 - Added ARIA Name to VS Code Status Bar Item
**Learning:** The `vscode.StatusBarItem` does not provide an explicit ARIA label property but uses the `name` property for screen readers and the status bar context menu.
**Action:** When adding or maintaining status bar items in VS Code extensions, ensure the `name` property is set for better accessibility.
