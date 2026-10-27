# Verified Hermes hook contract

- **Verified:** 2026-08-03
- **Installed source:** the Hermes Agent installation selected by the current runtime environment.

LedgerMind uses the public plugin registration surface from
`hermes_cli.plugins.PluginContext.register_hook(hook_name, callback)`.
Callbacks are invoked with keyword arguments and Hermes isolates callback
exceptions in `PluginManager.invoke_hook`.

## Hooks used

| Hook | Verified call site | Arguments used by LedgerMind |
|---|---|---|
| `pre_llm_call` | `agent/turn_context.py` | `session_id`, `task_id`, `turn_id`, `user_message`, `conversation_history`, `is_first_turn`, `model`, `platform`, `parent_session_id`, `sender_id` |
| `pre_tool_call` | `model_tools.py` / `hermes_cli.plugins.resolve_pre_tool_block` | `tool_name`, `args`, `task_id`, `session_id`, `tool_call_id`, `turn_id`, `api_request_id` |
| `post_tool_call` | `model_tools.py::_emit_post_tool_call_hook` | `tool_name`, `args`, `result`, `task_id`, `session_id`, `tool_call_id`, `turn_id`, `api_request_id`, `duration_ms`, `status`, `error_type`, `error_message` |
| `post_llm_call` | `agent/turn_finalizer.py` | `session_id`, `task_id`, `turn_id`, `user_message`, `assistant_response`, `conversation_history`, `model`, `platform` |
| `on_session_end` | Hermes lifecycle registry | observer-only shutdown callback; accepts keyword arguments and ignores unknown fields |

## Safety and behavior constraints

- `pre_llm_call` may return `{"context": "..."}` or a string. LedgerMind returns
  only a short, minimal `ContextView` rendering and fails open on transport errors.
- `pre_tool_call` is observational for LedgerMind and returns `None`; it never
  blocks or rewrites tool execution.
- `post_tool_call` and `post_llm_call` are observational. They do not call a
  model and do not perform retry loops.
- Hermes sends plugin-hook diagnostics to its own logging path; LedgerMind does
  not log raw arguments, results, conversation payloads, or provider secrets.
- `conversation_history` is treated as a read-only sequence. The adapter keeps
  its own in-memory round state and produces one validated RawRound with
  `schema_version=2`.
