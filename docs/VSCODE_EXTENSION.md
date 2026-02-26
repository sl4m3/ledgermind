# VS Code Hardcore Zero-Touch

The LedgerMind VS Code extension provides the highest level of autonomous
memory integration by moving from a reactive "Pull" model to a proactive
"Push" model.

---

## Overview

Unlike standard MCP integrations that require the AI model to manually call 
tools, the VS Code extension works invisibly in the background. It ensures
that your agent always has the latest project context and that every 
interaction is recorded without manual intervention or extra prompt tokens.

---

## Core Features

### 1. Shadow Context Injection
The extension maintains a hidden file named `ledgermind_context.md` in your
project root. This file is updated automatically whenever you:
- Save a file.
- Switch between editor tabs.
- Record a new decision.

When using agents like **Roo Code (Cline)**, they are configured to read this
file at the start of every task, providing them with "instant memory" of 
previous decisions and project state.

### 2. Full Conversation Logging
The extension listens to the native VS Code chat API. It automatically
captures both your prompts and the AI's responses, sending them to the 
Episodic Store. This covers:
- VS Code Copilot Chat.
- Built-in AI participants.
- Any extension using the standard chat provider.

### 3. Terminal Monitoring
Any output printed to the VS Code terminal is analyzed. This allows 
LedgerMind to "see" and remember:
- Build errors and stack traces.
- Test results (successes and failures).
- Deployment logs.

### 4. File System Watcher
Every time you save a document, the extension records a "save event" with a 
summary of the file changed. This builds a rich history of your coding
activity.

---

## Installation

You can install the extension and configure your environment with a single
command:

```bash
ledgermind install vscode --path /path/to/your/project
```

This command will:
1. Copy the extension to your `~/.vscode/extensions` folder.
2. Attempt to compile the extension (requires `npm`).
3. Configure **Roo Code (Cline)** to use LedgerMind as an MCP server.
4. Inject a **Custom Instruction** into Roo Code to read the context file.

---

## Manual Configuration for Continue.dev

If you use **Continue**, add the following to your `.continue/config.json`:

```json
{
  "contextProviders": [
    {
      "name": "file",
      "options": {
        "fileName": "ledgermind_context.md"
      }
    }
  ]
}
```

Then, you can reference the memory context by typing `@ledgermind_context.md`
in your chat.
