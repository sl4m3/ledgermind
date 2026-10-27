"""Durable, asynchronous retrieval usage delivery through the existing outbox."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from ledgermind_local.persistence import SQLiteUnitOfWork

from .contracts import RecordRetrievalOutcomeCommand, RetrieveContextCommand


class QueuedContextGateway:
    """Keep recall synchronous, but persist its usage before returning the view.

    The event records service-selected values, not host-confirmed visibility.
    Only identifiers are stored here, never a second copy of knowledge text.
    CoreCommandWorker owns delivery/retries; a crash after Core commit safely
    replays the same event key without an in-memory background task.
    """

    def __init__(self, gateway, database_path: str | Path) -> None:
        self.gateway = gateway
        self.database_path = database_path

    def retrieve_context(self, request: RetrieveContextCommand):
        return self.gateway.retrieve_context(request)

    def enqueue_retrieval_outcome(
        self, memory_space_id: str, command: RecordRetrievalOutcomeCommand
    ) -> str:
        payload = json.dumps(
            command.to_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
        identity = (
            "retrieval-usage:"
            + hashlib.sha256(command.retrieval_request_id.encode()).hexdigest()
        )
        with SQLiteUnitOfWork(self.database_path, write_transaction=True) as uow:
            stored = uow.raw_rounds.create_core_command(
                command_id=str(uuid.uuid4()),
                command_type="record_retrieval_outcome",
                memory_space_id=memory_space_id,
                idempotency_key=identity,
                payload_json=payload,
                payload_digest=digest,
            )
            uow.commit()
        return stored.command_id
