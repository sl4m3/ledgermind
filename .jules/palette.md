## 2025-03-05 - Added ARIA Name to VS Code Status Bar Item
**Learning:** The `vscode.StatusBarItem` does not provide an explicit ARIA label property but uses the `name` property for screen readers and the status bar context menu.
**Action:** When adding or maintaining status bar items in VS Code extensions, ensure the `name` property is set for better accessibility.

## 2025-03-05 - Added ARIA Label and Role to VS Code Status Bar Item
**Learning:** While `StatusBarItem.name` sets the internal name for the context menu, screen readers require the explicit setting of `accessibilityInformation` (which provides `label` and `role`) to accurately announce the item and its current state (e.g., when it switches to a "busy" or "syncing" state).
**Action:** When creating or dynamically updating a `StatusBarItem` in a VS Code extension, always configure and update `accessibilityInformation` alongside changes to `text` or `tooltip` to ensure robust screen reader support.
