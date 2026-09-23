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

export const LedgerMindPlugin = async ({ directory }) => {
  const lastText = new Map()
  const contextBySession = new Map()
  return {
    "chat.message": async (input, output) => {
      const prompt = textParts(output.parts)
      const response = bridge("UserPromptSubmit", {
        session_id: input.sessionID, cwd: directory, prompt,
      })
      const context = response?.hookSpecificOutput?.additionalContext
      if (context) contextBySession.set(input.sessionID, context)
      else contextBySession.delete(input.sessionID)
    },
    "experimental.chat.system.transform": async (input, output) => {
      const context = contextBySession.get(input.sessionID)
      if (context) output.system.push(context)
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
        if (part?.sessionID && part?.type === "text" && part?.text) lastText.set(part.sessionID, part.text)
      }
      if (event.type === "session.idle") {
        const sessionID = event.properties?.sessionID
        const response = lastText.get(sessionID)
        if (response) bridge("assistant", { session_id: sessionID, response })
        lastText.delete(sessionID)
        contextBySession.delete(sessionID)
        // OpenCode awaits the idle event handler even in `opencode run` mode,
        // so use Stop here: it durably enqueues the round and synchronously
        // flushes ready delivery before the short-lived process exits.
        bridge("Stop", { session_id: sessionID, cwd: directory })
      }
    },
  }
}
