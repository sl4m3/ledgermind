import { spawnSync } from "node:child_process"

// Replaced by the signed platform-bundle builder during installation.
const COMMAND = "__LEDGERMIND_COMMAND__"
const CONFIG = "__LEDGERMIND_CONFIG__"

function bridge(event, payload) {
  const result = spawnSync(COMMAND, ["integration-hook", "--config", CONFIG, "--event", event], {
    input: JSON.stringify(payload ?? {}), encoding: "utf8", timeout: 10000, stdio: ["pipe", "pipe", "ignore"],
  })
  if (result.status !== 0 || !result.stdout) return {}
  try { return JSON.parse(result.stdout) } catch { return {} }
}

function textParts(parts) {
  return (parts ?? []).filter((part) => part?.type === "text").map((part) => part.text).join("\n")
}

// Per-session round state shared by the legacy hook map and the setup() adapter.
function createRound(directory) {
  const contextBySession = new Map()
  const textBySession = new Map()
  const finished = new Set()

  const start = (sessionID) => {
    if (!sessionID) return
    finished.delete(sessionID)
    textBySession.delete(sessionID)
  }

  const remember = (sessionID, key, text) => {
    if (!sessionID || !text) return
    let parts = textBySession.get(sessionID)
    if (!parts) {
      parts = new Map()
      textBySession.set(sessionID, parts)
    }
    parts.set(key, text)
  }

  const finish = (sessionID) => {
    if (!sessionID || finished.has(sessionID)) return
    finished.add(sessionID)
    const parts = textBySession.get(sessionID)
    const response = parts ? [...parts.values()].join("\n") : ""
    contextBySession.delete(sessionID)
    textBySession.delete(sessionID)
    if (response) bridge("assistant", { session_id: sessionID, response })
    // OpenCode awaits the idle/terminal hook even in `opencode run` mode,
    // so use Stop here: it durably enqueues the round and synchronously
    // flushes ready delivery before the short-lived process exits.
    bridge("Stop", { session_id: sessionID, cwd: directory })
  }

  return {
    start,
    remember,
    finish,
    setContext(sessionID, context) {
      if (!sessionID) return
      if (context) contextBySession.set(sessionID, context)
      else contextBySession.delete(sessionID)
    },
    pushContext(sessionID, system) {
      const context = contextBySession.get(sessionID)
      if (context) system.push({ type: "text", text: context })
    },
  }
}

// Legacy OpenCode: named factory returning the hook map.
export const LedgerMindPlugin = async ({ directory }) => {
  const round = createRound(directory)
  return {
    "chat.message": async (input, output) => {
      round.start(input.sessionID)
      const prompt = textParts(output.parts)
      const response = bridge("UserPromptSubmit", {
        session_id: input.sessionID, cwd: directory, prompt,
      })
      const context = response?.hookSpecificOutput?.additionalContext
      // The existing text part has a host-issued part ID and is durably kept
      // in message history. Capture above used the original user text.
      const firstTextPart = output.parts.find((part) => part?.type === "text")
      if (context && firstTextPart) firstTextPart.text += `\n\n${context}`
    },
    "tool.execute.before": async (input, output) => {
      bridge("PreToolUse", {
        session_id: input.sessionID, cwd: directory, tool_name: input.tool,
        tool_use_id: input.callID, tool_input: output.args,
      })
    },
    "tool.execute.after": async (input, output) => {
      bridge("PostToolUse", {
        session_id: input.sessionID, cwd: directory, tool_name: input.tool,
        tool_use_id: input.callID, tool_response: output,
      })
    },
    event: async ({ event }) => {
      if (event.type === "message.part.updated") {
        const part = event.properties?.part
        if (part?.sessionID && part?.type === "text" && part?.text) {
          // Legacy parts carry no role, so keep the latest text part per session.
          round.remember(part.sessionID, "last", part.text)
        }
      }
      if (event.type === "session.idle") {
        round.finish(event.properties?.sessionID)
      }
      if (event.type === "session.compacted") {
        const sessionID = event.properties?.sessionID
        if (sessionID) bridge("PostCompact", { session_id: sessionID, cwd: directory })
      }
      if (event.type === "session.deleted") {
        const sessionID = event.properties?.info?.id ?? event.properties?.sessionID
        if (sessionID) bridge("SessionReset", { session_id: sessionID, cwd: directory })
      }
    },
  }
}

// Current OpenCode validates the default export as { id, setup }. The extra
// legacy `server` entry on the same object keeps older OpenCode releases
// working: their default-detection path only looks for id/server.
export default {
  id: "ledgermind",
  server: LedgerMindPlugin,
  async setup(ctx) {
    const directory = ctx.location.directory
    const round = createRound(directory)

    await ctx.session.hook("prompt", (event) => {
      round.start(event.sessionID)
      const response = bridge("UserPromptSubmit", {
        session_id: event.sessionID, cwd: directory, prompt: event.prompt.text ?? "",
      })
      round.setContext(event.sessionID, response?.hookSpecificOutput?.additionalContext)
    })

    await ctx.session.hook("context", (event) => {
      round.pushContext(event.sessionID, event.system)
    })

    await ctx.tool.hook("execute.before", (event) => {
      bridge("PreToolUse", {
        session_id: event.sessionID, cwd: directory, tool_name: event.tool,
        tool_use_id: event.id, tool_input: event.input,
      })
    })

    await ctx.tool.hook("execute.after", (event) => {
      bridge("PostToolUse", {
        session_id: event.sessionID, cwd: directory, tool_name: event.tool,
        tool_use_id: event.id,
        tool_response: event.status === "completed" ? event.result : { error: event.error },
      })
    })

    const controller = new AbortController()
    void (async () => {
      for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
        const data = event.data ?? {}
        if (event.type === "session.execution.started") {
          round.start(data.sessionID)
          continue
        }
        if (event.type === "session.text.ended") {
          round.remember(data.sessionID, `${data.assistantMessageID}:${data.ordinal}`, data.text)
          continue
        }
        if (
          event.type === "session.execution.succeeded" ||
          event.type === "session.execution.failed" ||
          event.type === "session.execution.interrupted" ||
          event.type === "session.idle"
        ) {
          round.finish(data.sessionID)
          continue
        }
        if (event.type === "session.compaction.ended") {
          if (data.sessionID) bridge("PostCompact", { session_id: data.sessionID, cwd: directory })
          continue
        }
        if (event.type === "session.deleted" && data.sessionID) {
          bridge("SessionReset", { session_id: data.sessionID, cwd: directory })
        }
      }
    })().catch(() => {})
    return () => controller.abort()
  },
}
