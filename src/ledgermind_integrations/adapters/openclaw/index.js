import { spawnSync } from "node:child_process"
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry"

const COMMAND = "__LEDGERMIND_COMMAND__"
const CONFIG = "__LEDGERMIND_CONFIG__"

function bridge(event, payload) {
  const result = spawnSync(COMMAND, ["integration-hook", "--config", CONFIG, "--event", event], {
    input: JSON.stringify(payload ?? {}), encoding: "utf8", timeout: 10000, stdio: ["pipe", "pipe", "ignore"],
  })
  if (result.status !== 0 || !result.stdout) return {}
  try { return JSON.parse(result.stdout) } catch { return {} }
}

export default definePluginEntry({
  id: "ledgermind-memory",
  name: "LedgerMind Memory",
  description: "Local durable memory for OpenClaw agents",
  register(api) {
    api.on("before_prompt_build", async (event, ctx) => {
      const response = bridge("UserPromptSubmit", {
        session_id: ctx.sessionKey ?? ctx.sessionId ?? ctx.runId,
        prompt: event.prompt,
      })
      const context = response?.hookSpecificOutput?.additionalContext
      return context ? { prependContext: context } : undefined
    }, { timeoutMs: 10000 })
    api.on("before_tool_call", async (event, ctx) => {
      bridge("PreToolUse", {
        session_id: ctx.sessionKey ?? ctx.sessionId ?? ctx.runId,
        tool_name: event.toolName, tool_use_id: event.toolCallId, tool_input: event.params,
      })
    })
    api.on("after_tool_call", async (event, ctx) => {
      bridge("PostToolUse", {
        session_id: ctx.sessionKey ?? ctx.sessionId ?? ctx.runId,
        tool_name: event.toolName, tool_use_id: event.toolCallId,
        tool_response: event.result, error: event.error,
      })
    })
    api.on("llm_output", async (event, ctx) => {
      bridge("assistant", {
        session_id: ctx.sessionKey ?? ctx.sessionId ?? ctx.runId,
        response: event.lastAssistant ?? event.assistantTexts,
      })
    })
    api.on("agent_end", async (event, ctx) => {
      bridge("agent_end", {
        session_id: ctx.sessionKey ?? ctx.sessionId ?? ctx.runId,
        success: event.success,
      })
    }, { timeoutMs: 10000 })
  },
})
