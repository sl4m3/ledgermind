## 2026-04-26 - VS Code Interactive Status Bar Dismissal
**Learning:** Dismissing a persistent error state from the status bar via the bound command effectively clears the error state visually, but screen readers might not immediately catch the state change unless explicitly decoupled and re-announced or when the state simply clears via explicit action. In our case, clearing error via the output channel explicitly solves this.
**Action:** Always provide explicit user interactions to dismiss persistent error states.
## 2026-04-30 - Surfacing Background Environment Errors
**Learning:** When background operations (like execFile) fail due to missing dependencies (like ENOENT for a CLI tool), silently logging to an output channel and turning the status bar red is insufficient. Users might not realize the environment setup is incomplete.
**Action:** Promote critical environment errors (like missing CLIs) to visible toast notifications (e.g., vscode.window.showErrorMessage) at least once so users have actionable steps (like 'pip install') to resolve the issue.
