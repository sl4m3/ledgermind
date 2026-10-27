"""Read-only, schema-tolerant observation of Hermes state.db messages."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ledgermind_protocol import build_resolution_extension


class HermesStateReader:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def session_events(self, session_id: str) -> list[dict[str, Any]]:
        """Return the legacy full-session view for diagnostics only.

        Pending recovery must use :meth:`round_events`, which applies the
        persisted round boundaries before converting rows to events.
        """

        rows, columns = self._query_rows(session_id)
        return self._events_from_rows(rows, columns, trim_to_round=False)

    def round_events(
        self,
        session_id: str,
        first_message_id: int | None = None,
        last_message_id: int | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        user_message_id: int | None = None,
        assistant_message_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read exactly one pending round from Hermes' message table.

        Message IDs are the primary boundary because they are monotonic within
        ``state.db``.  Timestamp boundaries are used when hooks could not
        expose IDs.  The final assistant message terminates the recovered
        event sequence so a broad timestamp window cannot absorb a later turn.
        """

        rows, columns = self._query_rows(
            session_id,
            first_message_id=first_message_id,
            last_message_id=last_message_id,
            started_at=started_at,
            completed_at=completed_at,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
        )
        return self._events_from_rows(
            rows,
            columns,
            trim_to_round=True,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
        )

    def resolution_extension(
        self,
        session_id: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        first_message_id: int | None = None,
        last_message_id: int | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        user_message_id: int | None = None,
        assistant_message_id: int | None = None,
        project_id: str | None = None,
        repository_id: str | None = None,
        task_id: str | None = None,
        working_directory: str | None = None,
        repository_root: str | None = None,
        repository_mapping: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Build the canonical resolution extension from Hermes metadata."""

        rows, columns = self._query_rows(
            session_id,
            first_message_id=first_message_id,
            last_message_id=last_message_id,
            started_at=started_at,
            completed_at=completed_at,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
        )
        row_metadata = [self._resolution_metadata(row, columns) for row in rows]
        if metadata is not None:
            row_metadata.append(dict(metadata))
        return build_resolution_extension(
            session_id,
            metadata=row_metadata,
            project_id=project_id,
            repository_id=repository_id,
            task_id=task_id,
            working_directory=working_directory,
            repository_root=repository_root,
            repository_mapping=repository_mapping,
            base_path=self.path.parent,
        )

    def _connect(self) -> sqlite3.Connection | None:
        if not self.path.exists():
            return None
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=1.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _query_rows(
        self,
        session_id: str,
        *,
        first_message_id: int | None = None,
        last_message_id: int | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        user_message_id: int | None = None,
        assistant_message_id: int | None = None,
    ) -> tuple[list[sqlite3.Row], set[str]]:
        connection = self._connect()
        if connection is None:
            return [], set()
        try:
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(messages)")}
            if not {"id", "role", "session_id"}.issubset(columns):
                return [], columns
            selected_names = [
                name
                for name in (
                    "id",
                    "role",
                    "content",
                    "api_content",
                    "tool_call_id",
                    "tool_name",
                    "tool_calls",
                    "timestamp",
                    "created_at",
                    "finish_reason",
                    "effect_disposition",
                    "project_id",
                    "repository_id",
                    "task_id",
                    "conversation_id",
                    "project",
                    "repository",
                    "task",
                    "repo_id",
                    "repo",
                    "working_directory",
                    "repository_root",
                    "git_root",
                    "cwd",
                    "workdir",
                    "metadata",
                    "session_metadata",
                    "resolution_context",
                )
                if name in columns
            ]
            timestamp_column = next(
                (name for name in ("timestamp", "created_at") if name in columns), None
            )
            clauses = ["session_id = ?"]
            parameters: list[object] = [session_id]
            lower_message_id = first_message_id
            if lower_message_id is None:
                lower_message_id = user_message_id
            upper_message_id = last_message_id
            if upper_message_id is None:
                upper_message_id = assistant_message_id
            if lower_message_id is not None:
                clauses.append("id >= ?")
                parameters.append(lower_message_id)
            if upper_message_id is not None:
                clauses.append("id <= ?")
                parameters.append(upper_message_id)
            if timestamp_column is not None and lower_message_id is None:
                start_epoch = self._timestamp_value(started_at)
                if start_epoch is not None:
                    clauses.append(f"{timestamp_column} >= ?")
                    parameters.append(start_epoch)
            if timestamp_column is not None and upper_message_id is None:
                end_epoch = self._timestamp_value(completed_at)
                if end_epoch is not None:
                    clauses.append(f"{timestamp_column} <= ?")
                    parameters.append(end_epoch)
            sql = (
                f"SELECT {', '.join(selected_names)} FROM messages "
                + "WHERE "
                + " AND ".join(clauses)
                + " ORDER BY id ASC"
            )
            return connection.execute(sql, parameters).fetchall(), columns
        finally:
            connection.close()

    @classmethod
    def _events_from_rows(
        cls,
        rows: Sequence[sqlite3.Row],
        columns: set[str],
        *,
        trim_to_round: bool,
        user_message_id: int | None = None,
        assistant_message_id: int | None = None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for row in rows:
            events.extend(cls._row_events(row, columns))
        if not events:
            return []
        if trim_to_round:
            events = cls._trim_to_round(events, user_message_id)
            cls._link_anonymous_tool_calls(events)
        final_index = cls._final_assistant_index(
            events,
            assistant_message_id=assistant_message_id,
            prefer_first=trim_to_round,
        )
        if final_index is not None:
            events = events[: final_index + 1]
            events[final_index]["final"] = True
        for event in events:
            event.pop("_terminal_assistant", None)
            event.pop("_synthetic_tool_call", None)
        return events

    @classmethod
    def _row_events(cls, row: sqlite3.Row, columns: set[str]) -> list[dict[str, Any]]:
        row_id = str(row["id"])
        role = str(row["role"])
        content = cls._row_content(row, columns)
        tool_calls = cls._decode_json(row["tool_calls"]) if "tool_calls" in columns else None
        result: list[dict[str, Any]] = []
        if role == "tool" or (row["tool_call_id"] if "tool_call_id" in columns else None):
            tool_call_id = (
                str(row["tool_call_id"])
                if "tool_call_id" in columns and row["tool_call_id"]
                else f"{row_id}:call"
            )
            result.append(
                {
                    "event_id": row_id,
                    "kind": "tool_result",
                    "tool_call_id": tool_call_id,
                    "status": cls._result_status(content, row, columns),
                    "content": content if content is not None else "",
                }
            )
            return result
        if role == "assistant" and tool_calls:
            if content not in (None, ""):
                result.append(
                    {
                        "event_id": row_id,
                        "kind": "message",
                        "role": "assistant",
                        "content": content,
                        "_terminal_assistant": False,
                    }
                )
            for index, call in enumerate(cls._as_call_list(tool_calls)):
                result.append(cls._tool_call_event(row_id, index, call, row, columns))
            return result
        if role not in {"user", "assistant", "system"}:
            # A legacy unknown role must not become a canonical ``tool``
            # message.  Preserve the observable text as a neutral system
            # message instead of inventing semantic fields.
            role = "system"
        event = {
            "event_id": row_id,
            "kind": "message",
            "role": role,
            "content": content if content is not None else "",
        }
        if role == "assistant":
            event["_terminal_assistant"] = True
        return [event]

    @classmethod
    def _tool_call_event(
        cls,
        row_id: str,
        index: int,
        call: object,
        row: sqlite3.Row,
        columns: set[str],
    ) -> dict[str, Any]:
        call_mapping = call if isinstance(call, Mapping) else {}
        function = call_mapping.get("function")
        function_mapping = function if isinstance(function, Mapping) else {}
        call_id = call_mapping.get("call_id") or call_mapping.get("id")
        synthetic = not isinstance(call_id, str) or not call_id.strip()
        if synthetic:
            call_id = f"{row_id}:call:{index}"
        tool_name = function_mapping.get("name") or call_mapping.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            tool_name = row["tool_name"] if "tool_name" in columns else "unknown"
        if not isinstance(tool_name, str) or not tool_name.strip():
            tool_name = "unknown"
        arguments = function_mapping.get("arguments", call_mapping.get("arguments", {}))
        if isinstance(arguments, str):
            decoded_arguments = cls._decode_json(arguments)
            arguments = decoded_arguments if decoded_arguments is not None else arguments
        call_id_text = str(call_id).strip()
        event = {
            "event_id": f"{row_id}:tool_call:{index}",
            "kind": "tool_call",
            "tool_call_id": call_id_text,
            "tool_name": tool_name.strip(),
            "arguments": arguments if arguments is not None else {},
        }
        if synthetic:
            event["_synthetic_tool_call"] = True
        return event

    @classmethod
    def _trim_to_round(
        cls, events: list[dict[str, Any]], user_message_id: int | None = None
    ) -> list[dict[str, Any]]:
        if user_message_id is not None:
            target_id = str(user_message_id)
            for index, event in enumerate(events):
                if (
                    event.get("kind") == "message"
                    and event.get("role") == "user"
                    and event.get("event_id") == target_id
                ):
                    return events[index:]
        user_indices = [
            index
            for index, event in enumerate(events)
            if event.get("kind") == "message" and event.get("role") == "user"
        ]
        if len(user_indices) > 1:
            events = events[user_indices[-1] :]
        return events

    @staticmethod
    def _final_assistant_index(
        events: Sequence[Mapping[str, Any]],
        *,
        assistant_message_id: int | None,
        prefer_first: bool,
    ) -> int | None:
        if assistant_message_id is not None:
            target_id = str(assistant_message_id)
            for index, event in enumerate(events):
                if (
                    event.get("kind") == "message"
                    and event.get("role") == "assistant"
                    and event.get("event_id") == target_id
                ):
                    return index
        indices = range(len(events)) if prefer_first else range(len(events) - 1, -1, -1)
        for index in indices:
            event = events[index]
            if (
                event.get("kind") == "message"
                and event.get("role") == "assistant"
                and event.get("_terminal_assistant", True)
            ):
                return index
        return None

    @staticmethod
    def _link_anonymous_tool_calls(events: list[dict[str, Any]]) -> None:
        known_call_ids = {
            str(event.get("tool_call_id"))
            for event in events
            if event.get("kind") == "tool_call"
            and not event.get("_synthetic_tool_call")
        }
        anonymous_calls = [
            event
            for event in events
            if event.get("kind") == "tool_call" and event.get("_synthetic_tool_call")
        ]
        unmatched_results = [
            event
            for event in events
            if event.get("kind") == "tool_result"
            and str(event.get("tool_call_id")) not in known_call_ids
        ]
        for call, result in zip(anonymous_calls, unmatched_results):
            call["tool_call_id"] = result["tool_call_id"]

    @staticmethod
    def _row_content(row: sqlite3.Row, columns: set[str]) -> object:
        if "api_content" in columns and row["api_content"]:
            return row["api_content"]
        return row["content"] if "content" in columns else ""

    @staticmethod
    def _resolution_metadata(row: sqlite3.Row, columns: set[str]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for name in (
            "project_id",
            "repository_id",
            "task_id",
            "conversation_id",
            "project",
            "repository",
            "task",
            "repo_id",
            "repo",
            "working_directory",
            "repository_root",
            "git_root",
            "cwd",
            "workdir",
        ):
            if name in columns and row[name] is not None:
                metadata[name] = row[name]
        for name in ("metadata", "session_metadata", "resolution_context"):
            if name not in columns:
                continue
            decoded = HermesStateReader._decode_json(row[name])
            if isinstance(decoded, Mapping):
                metadata[name] = decoded
        return metadata

    @staticmethod
    def _as_call_list(value: object) -> list[object]:
        if isinstance(value, list):
            return value
        if isinstance(value, Mapping):
            return [value]
        return []

    @staticmethod
    def _decode_json(value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _result_status(
        content: object, row: sqlite3.Row, columns: set[str]
    ) -> str:
        if "effect_disposition" in columns:
            disposition = row["effect_disposition"]
            if isinstance(disposition, str):
                normalized = disposition.strip().lower()
                if normalized in {"success", "ok", "completed"}:
                    return "success"
                if normalized in {"error", "failed", "failure"}:
                    return "error"
                if normalized in {"cancelled", "canceled"}:
                    return "cancelled"
        if isinstance(content, Mapping) and content.get("error"):
            return "error"
        if isinstance(content, str):
            decoded = HermesStateReader._decode_json(content)
            if isinstance(decoded, Mapping) and decoded.get("error"):
                return "error"
        return "success"

    @staticmethod
    def _timestamp_value(value: str | None) -> float | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
