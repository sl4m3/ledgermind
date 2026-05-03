## 2026-04-26 - VS Code Interactive Status Bar Dismissal
**Learning:** Dismissing a persistent error state from the status bar via the bound command effectively clears the error state visually, but screen readers might not immediately catch the state change unless explicitly decoupled and re-announced or when the state simply clears via explicit action. In our case, clearing error via the output channel explicitly solves this.
**Action:** Always provide explicit user interactions to dismiss persistent error states.

## 2026-04-26 - Actionable Toasts for Missing Dependencies
**Learning:** When background operations fail due to missing external CLI dependencies (e.g., ENOENT on execFile), surfacing the failure with a one-time actionable toast notification (`vscode.window.showErrorMessage`) rather than just silently turning the status bar red provides users with exactly how to fix their environment.
**Action:** Use actionable toast notifications to guide users in resolving missing dependencies.
