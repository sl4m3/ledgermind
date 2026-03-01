# VS Code Extension

Complete guide to the LedgerMind VS Code extension for seamless IDE integration.

---

## Introduction

The LedgerMind VS Code extension brings autonomous memory management directly into your development workflow. It provides:

- **Shadow Context Injection** — Automatic memory retrieval without prompts
- **Terminal Monitoring** — Capture command output as evidence
- **Chat Participant** — Natural language memory interactions
- **Hardcore Mode** — Fully automated context injection
- **Multi-namespace support** — Isolate memories by project or team

**Audience**:
- **VS Code Developers** integrating memory management into their workflow
- **DevOps Engineers** automating development workflows
- **Software Architects** maintaining decision history

**Quick Reference**:

| Feature | Description | Configuration |
|---------|-------------|----------------|
| **Hardcore Mode** | Auto-inject context | `hardcoreMode: true` |
| **Terminal Monitoring** | Capture terminal output | `terminalMonitoring: true` |
| **Chat Participant** | Natural language tools | `chatParticipant: true` |
| **Namespace** | Memory isolation | `namespace: "project-name"` |
| **Relevance Threshold** | Minimum relevance | `relevanceThreshold: 0.7` |

---

## Installation

### VS Code Marketplace

```bash
# Search and install
code --install-extension ledgermind.vscode

# Or search in Extensions view (Ctrl+Shift+X)
# Search for: "ledgermind"
```

### Manual Installation

```bash
# Clone repository
git clone https://github.com/ledgermind/ledgermind-vscode
cd ledgermind-vscode

# Install dependencies
npm install

# Package extension
npm run package

# Install .vsix file
code --install-extension ledgermind-vscode-*.vsix
```

### Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| **VS Code** | 1.80+ | Stable or Insiders |
| **Node.js** | 18+ | For building from source |
| **LedgerMind** | 3.1.0+ | MCP server running locally |

---

## Configuration

### Settings Location

Extension settings are stored in `settings.json`:

```json
// ~/.config/Code/User/settings.json (Linux)
// ~/Library/Application Support/Code/User/settings.json (macOS)
// %APPDATA%\Code\User\settings.json (Windows)
```

### Workspace Settings

Project-specific settings in `.vscode/settings.json`:

```json
{
  "ledgermind.memoryPath": "/absolute/path/to/.ledgermind",
  "ledgermind.namespace": "backend-api",
  "ledgermind.hardcoreMode": false,
  "ledgermind.terminalMonitoring": true,
  "ledgermind.chatParticipant": true,
  "ledgermind.relevanceThreshold": 0.7
}
```

### Complete Configuration Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `memoryPath` | string | `"~/.ledgermind"` | Absolute path to LedgerMind memory |
| `namespace` | string | `"default"` | Memory namespace for isolation |
| `hardcoreMode` | boolean | `false` | Auto-inject context without UI |
| `terminalMonitoring` | boolean | `false` | Capture terminal output |
| `chatParticipant` | true | Enable chat integration |
| `relevanceThreshold` | number | `0.7` | Minimum relevance (0.0-1.0) |
| `customHooks` | object | `{}` | Custom hook functions |

---

## Features

### Hardcore Mode

**Purpose**: Automatically inject relevant memory into LLM prompts without showing it in the UI.

**Configuration**:

```json
{
  "ledgermind.hardcoreMode": true
}
```

**Behavior**:

When `hardcoreMode` is enabled:

1. Before each AI prompt, context is automatically retrieved
2. Context is injected invisibly into the prompt
3. User sees no indication of injection
4. AI receives memory as additional context

**Use Cases**:

| Scenario | Description |
|----------|-------------|
| **Automated Refactoring** | Context is silently provided for code changes |
| **Continuous Integration** | AI agents make informed decisions without prompts |
| **Background Tasks** | Automated workflows access memory seamlessly |

**Example**:

```typescript
// Extension automatically injects context
// before AI receives this prompt:
"How should I structure the API response?"

// AI actually receives:
"Context from ledgermind:
- Use standardized error responses
- Include request ID for tracing
- Follow RESTful conventions

How should I structure the API response?"
```

**Trade-offs**:

| Aspect | Hardcore Mode On | Hardcore Mode Off |
|--------|------------------|-------------------|
| **Visibility** | Invisible to user | Shown in UI |
| **Control** | Automatic | Manual confirmation |
| **Use Case** | Automation | Human oversight |

---

### Terminal Monitoring

**Purpose**: Automatically capture terminal output as evidence for decisions.

**Configuration**:

```json
{
  "ledgermind.terminalMonitoring": true,
  "ledgermind.terminalCapture": {
    "enabled": true,
    "captureOnCommand": true,
    "captureOnOutput": true,
    "includeErrors": true,
    "excludePatterns": ["password", "api.*key"]
  }
}
```

**Behavior**:

| Event | Captured? | Description |
|-------|-----------|-------------|
| **Command Execution** | ✓ | Commands run in terminal |
| **Output** | ✓ | Command output/results |
| **Errors** | ✓ | Error messages |
| **Duration** | ✓ | Command execution time |

**Captured Content**:

```typescript
// Example captured event
{
  "kind": "tool_call",
  "description": "npm test",
  "timestamp": "2024-01-20T15:30:00Z",
  "metadata": {
    "command": "npm test",
    "exitCode": 0,
    "duration_ms": 1200,
    "output": "PASS: All tests passed"
  }
}
```

**Exclusion Patterns**:

Patterns are regex matched against command and output:

```json
{
  "excludePatterns": [
    "password",           // Exclude lines containing "password"
    "api.*key",           // Exclude lines matching "api.*key"
    "secret.*=.*"         // Exclude lines with "secret=" pattern
  ]
}
```

**Evidence Linking**:

Captured events are automatically linked to relevant decisions:

```typescript
// Terminal command: "npm run test-api"
// Linked to decision: "Use standardized error responses"
// Reason: Both relate to API behavior
```

---

### Chat Participant

**Purpose**: Natural language interaction with LedgerMind memory through VS Code's AI Chat.

**Configuration**:

```json
{
  "ledgermind.chatParticipant": true
}
```

**Usage**:

1. Open AI Chat (`Ctrl+Shift+I` / `Cmd+Shift+I`)
2. Select "LedgerMind" from participants
3. Ask natural language questions

**Available Commands**:

| Command | Description | Example |
|---------|-------------|---------|
| `search` | Find relevant decisions | `"search for database decisions"` |
| `record` | Record a new decision | `"record decision: Use PostgreSQL"` |
| `history` | Get decision evolution | `"show history of abc123"` |
| `recent` | Get recent events | `"show recent events"` |
| `help` | Show available commands | `"help"` |

**Example Conversations**:

```typescript
// User: "What decisions have we made about the API?"
// LedgerMind: "Here are 3 relevant decisions:
// 1. Use standardized error responses (0.92 score)
// 2. Include request ID for tracing (0.85 score)
// 3. Follow RESTful conventions (0.78 score)
//
// Would you like details on any of these?"

// User: "Tell me more about the first one"
// LedgerMind: "**Use standardized error responses**
//
// Target: api
// Rationale: Consistent error handling improves debugging...
// Created: 2024-01-15
// Confidence: 0.95
//
// Evidence: Linked to 5 events including test failures"

// User: "Record a new decision: Add rate limiting"
// LedgerMind: "I'll help you record that decision.
//
// Please provide:
// 1. Target component (e.g., api, database)
// 2. Rationale (why make this decision?)
// 3. Expected consequences"
```

---

### Namespace Isolation

**Purpose**: Separate memories by project, team, or domain.

**Configuration**:

```json
{
  "ledgermind.namespace": "backend-api"
}
```

**Namespace Scenarios**:

| Namespace | Use Case | Example |
|-----------|----------|---------|
| `default` | Personal workspace | Individual developer |
| `backend-api` | Backend API team | API-specific decisions |
| `frontend` | Frontend team | UI/UX decisions |
| `infrastructure` | DevOps team | Infrastructure choices |
| `security` | Security team | Security policies |

**Namespace Behavior**:

```typescript
// Search in "backend-api" namespace
await client.call_tool("search_decisions", {
  "query": "database",
  "namespace": "backend-api"  // Only searches backend-api decisions
})

// Record in "backend-api" namespace
await client.call_tool("record_decision", {
  "title": "Use connection pooling",
  "target": "database",
  "rationale": "...",
  "namespace": "backend-api"  // Recorded in backend-api
})
```

**Multi-Workspace Setup**:

```json
// .vscode/settings.json
{
  "ledgermind.memoryPath": "${workspaceFolder}/.ledgermind",
  "ledgermind.namespace": "${workspaceFolderBasename}"
}

// Result: Each workspace gets isolated memory
// workspace-1/ → namespace: "workspace-1"
// workspace-2/ → namespace: "workspace-2"
```

---

### Relevance Threshold

**Purpose**: Control minimum relevance score for context injection.

**Configuration**:

```json
{
  "ledgermind.relevanceThreshold": 0.7
}
```

**Threshold Values**:

| Value | Behavior | Use Case |
|-------|----------|----------|
| `0.4` (fuzzy) | Include loosely related items | Discovery, exploration |
| `0.7` (balanced) | Include moderately relevant items | General development |
| `0.9` (strict) | Include only highly relevant items | Precision-critical tasks |

**Impact**:

```typescript
// Query: "database migrations"

// Threshold: 0.4 (fuzzy)
Results: 8 decisions (including loosely related)

// Threshold: 0.7 (balanced)
Results: 4 decisions (directly related)

// Threshold: 0.9 (strict)
Results: 1 decision (exact match)
```

---

## Custom Hooks

**Purpose**: Override default extension behavior with custom functions.

**Configuration**:

```json
{
  "ledgermind.customHooks": {
    "beforePrompt": "custom-context-injection",
    "afterTool": "custom-post-processing"
  }
}
```

### Hook Types

| Hook | Timing | Purpose |
|------|----------|---------|
| `beforePrompt` | Before user submits prompt | Modify context injection |
| `afterTool` | After AI tool call | Process tool results |
| `beforeSubmit` | Before code submission | Add validation |

### Custom Hook Implementation

```typescript
// custom-hooks.ts
export function customContextInjection(
  prompt: string,
  context: string
): string {
  // Custom logic to modify context
  const modifiedContext = filterByTarget(context, "api");

  return `${modifiedContext}\n\n${prompt}`;
}

export function customPostProcessing(
  toolCall: ToolCall,
  result: any
): any {
  // Process tool call results
  if (toolCall.name === "record_decision") {
    logDecision(result);
  }

  return result;
}
```

### Registering Hooks

```typescript
// extension.ts
import * as hooks from "./custom-hooks";

export function activate(context: vscode.ExtensionContext) {
  // Register custom hooks
  const ledgermind = getLedgermindAPI();

  ledgermind.registerHook("beforePrompt", hooks.customContextInjection);
  ledgermind.registerHook("afterTool", hooks.customPostProcessing);
}
```

---

## Commands

### Available Commands

| Command | ID | Description |
|---------|----|-------------|
| **Search Decisions** | `ledgermind.searchDecisions` | Open search dialog |
| **Record Decision** | `ledgermind.recordDecision` | Open decision creation dialog |
| **View Decision History** | `ledgermind.viewHistory` | View decision evolution |
| **Get Recent Events** | `ledgermind.getRecentEvents` | View recent activity |
| **Sync to Git** | `ledgermind.syncGit` | Force Git sync |
| **Toggle Hardcore Mode** | `ledgermind.toggleHardcore` | Enable/disable auto-injection |
| **Toggle Terminal Monitoring** | `ledgermind.toggleTerminal` | Enable/disable terminal capture |
| **Clear Context Cache** | `ledgermind.clearCache` | Clear cached embeddings |

### Command Palette Usage

```typescript
// Open Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
// Type: "LedgerMind" to see all commands
```

### Keybindings

Add to `keybindings.json`:

```json
[
  {
    "key": "ctrl+alt+d",
    "command": "ledgermind.recordDecision"
  },
  {
    "key": "ctrl+alt+s",
    "command": "ledgermind.searchDecisions"
  },
  {
    "key": "ctrl+alt+h",
    "command": "ledgermind.viewHistory"
  }
]
```

---

## Troubleshooting

### Extension Not Loading

**Symptoms**:
- No LedgerMind commands in Command Palette
- No LedgerMind participant in AI Chat
- Errors in extension output

**Solutions**:

```bash
# 1. Check extension is installed
code --list-extensions | grep ledgermind

# 2. Check extension version
code --list-extensions --show-versions

# 3. Reload VS Code
code --reload

# 4. Check extension logs
View → Output → Select "LedgerMind" from dropdown

# 5. Check MCP server is running
ps aux | grep ledgermind

# 6. Verify memory path exists
ls -la ~/.ledgermind
```

### Context Not Injecting

**Symptoms**:
- AI responses don't use past decisions
- No memory context in prompts

**Solutions**:

```json
// 1. Check hardcore mode is enabled
{
  "ledgermind.hardcoreMode": true
}

// 2. Check relevance threshold
{
  "ledgermind.relevanceThreshold": 0.7  // Try lowering to 0.5
}

// 3. Check memory path
{
  "ledgermind.memoryPath": "/absolute/path/to/.ledgermind"
}

// 4. Verify MCP server connection
// View → Output → Select "LedgerMind"
// Look for: "Connected to MCP server"
```

### Terminal Monitoring Not Working

**Symptoms**:
- No events recorded from terminal
- Evidence not linked to decisions

**Solutions**:

```json
// 1. Check terminal monitoring is enabled
{
  "ledgermind.terminalMonitoring": true
}

// 2. Check terminal capture settings
{
  "ledgermind.terminalCapture": {
    "enabled": true,
    "captureOnCommand": true,
    "captureOnOutput": true
  }
}

// 3. Check exclusion patterns
{
  "ledgermind.terminalCapture": {
    "excludePatterns": []  // Temporarily clear exclusions
  }
}

// 4. Check terminal type
// Only integrated terminals are supported
// Terminal → New Terminal
```

### Namespace Conflicts

**Symptoms**:
- Decisions from one namespace appear in another
- Search results include unrelated decisions

**Solutions**:

```json
// 1. Verify namespace setting
{
  "ledgermind.namespace": "backend-api"  // Must be correct
}

// 2. Use absolute paths
{
  "ledgermind.memoryPath": "/absolute/path/to/.ledgermind"
}

// 3. Clear namespace cache
// Command Palette → "LedgerMind: Clear Context Cache"

// 4. Check MCP server configuration
ps aux | grep ledgermind
# Verify --namespace flag matches VS Code setting
```

---

## Best Practices

### Development Workflow

1. **Setup Namespace**
   ```json
   {
     "ledgermind.namespace": "my-project"
   }
   ```

2. **Enable Hardcore Mode** (for automated workflows)
   ```json
   {
     "ledgermind.hardcoreMode": true
   }
   ```

3. **Enable Terminal Monitoring** (for evidence)
   ```json
   {
     "ledgermind.terminalMonitoring": true
   }
   ```

4. **Set Relevance Threshold** (balance precision vs recall)
   ```json
   {
     "ledgermind.relevanceThreshold": 0.7
   }
   ```

### Code Review Workflow

1. **Search for Related Decisions**
   ```typescript
   // Command Palette → "LedgerMind: Search Decisions"
   // Query: "authentication", "authorization", "security"
   ```

2. **Review Decision History**
   ```typescript
   // Command Palette → "LedgerMind: View History"
   // See how decisions evolved over time
   ```

3. **Link Evidence**
   ```typescript
   // Terminal commands are automatically linked
   // View: "LedgerMind: Get Recent Events"
   ```

### Team Collaboration

1. **Shared Memory Path**
   ```json
   {
     "ledgermind.memoryPath": "/shared/team/.ledgermind"
   }
   ```

2. **Team Namespace**
   ```json
   {
     "ledgermind.namespace": "team-backend"
   }
   ```

3. **Sync to Remote Git**
   ```typescript
   // Command Palette → "LedgerMind: Sync to Git"
   // Ensures team sees latest decisions
   ```

---

## Advanced Configuration

### Multi-Root Workspace

```json
// .vscode/settings.json (workspace level)
{
  "ledgermind.namespace": "${workspaceFolderBasename}",
  "ledgermind.hardcoreMode": true
}

// Result: Each root folder gets isolated namespace
// root-folder-1/ → namespace: "root-folder-1"
// root-folder-2/ → namespace: "root-folder-2"
```

### Remote Development (SSH)

```json
// local .vscode/settings.json
{
  "ledgermind.memoryPath": "/remote/user/.ledgermind",
  "ledgermind.namespace": "remote-project"
}

// Run LedgerMind on remote machine
ssh user@remote "ledgermind run --path ~/.ledgermind"
```

### Custom Context Filter

```typescript
// custom-hooks.ts
export function filterByTarget(
  context: string,
  target: string
): string {
  const lines = context.split("\n");
  const filtered = lines.filter(line =>
    line.includes(`target: ${target}`)
  );

  return filtered.join("\n");
}

// Register hook
ledgermind.registerHook("beforePrompt", (prompt, context) => {
  const filteredContext = filterByTarget(context, "api");
  return `${filteredContext}\n\n${prompt}`;
});
```

---

## Performance Optimization

### Memory Path

```json
{
  // Use absolute path (faster than relative)
  "ledgermind.memoryPath": "/absolute/path/to/.ledgermind"
}
```

### Context Caching

```json
{
  // Cache embeddings for repeated queries
  "ledgermind.relevanceThreshold": 0.7,
  "ledgermind.hardcoreMode": true
}
```

### Terminal Capture

```json
{
  "ledgermind.terminalMonitoring": true,
  "ledgermind.terminalCapture": {
    "captureOnOutput": false  // Disable if not needed
  }
}
```

---

## Next Steps

For integration details:
- [Integration Guide](integration-guide.md) — Client integration patterns
- [MCP Tools](mcp-tools.md) — Complete tool reference

For configuration:
- [Configuration](configuration.md) — All configuration options
- [Architecture](architecture.md) — System internals

For general usage:
- [Quick Start](quickstart.md) — Getting started guide
- [API Reference](api-reference.md) — Python API

---

