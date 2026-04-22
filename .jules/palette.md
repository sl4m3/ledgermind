## 2024-04-10 - Consistent CLI Visual Feedback and Logging
**Learning:** Raw `print` statements mixed with `rich.console` and poor silent error handling disrupt the user experience, making diagnostic outputs feel unprofessional and difficult to read.
**Action:** Consistently use `rich.console` for diagnostic/error messages in the CLI and properly log silent parsing errors (`json.JSONDecodeError`) as warnings to maintain both visual consistency and robust debugging capability without overwhelming standard output.
## 2024-05-24 - Missing accessibility states for background tasks
**Learning:** In VS Code extensions, background watchers that execute silently can fail or hang without the user knowing. This breaks accessibility guidelines as screen readers and visual indicators do not alert the user to ongoing work or failures.
**Action:** Always wrap async or background processes (like `execFile`) with loading state handlers (e.g., `setBusy(true/false)`) and ensure error callbacks explicitly set error UI states (e.g., `setError(true)`) to provide consistent, accessible feedback via status bar items or ARIA labels.
## 2024-04-16 - Accessible Error State Management
**Learning:** Background process errors (like file watcher JSON parsing) need accessible visual cues via the status bar, and users need an interactive path to dismiss these error states (e.g. by clicking to open logs).
**Action:** Always wrap background processes with accessible error state triggers (`setError(true)`) and ensure the associated UI element's command can clear the error state.

## 2024-04-22 - Visual representation of background tasks in error states
**Learning:** Users and screen readers lose visibility of active background synchronization if an unacknowledged persistent error state entirely overrides the status bar.
**Action:** When overlapping states occur, dynamically combine icons and accessibility labels (e.g., error and active sync) to ensure both critical conditions remain visible.
