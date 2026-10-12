"""Bounded memory-only one-use previews. All state transitions are synchronous."""

import json
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import JsonValue

from ..action_protocol import CasaActionsProtocol
from .models import ActionResult

Group = Literal["actions", "messages", "uploads"]
Invocation = Callable[[CasaActionsProtocol, str], Awaitable[ActionResult]]
TTL_SECONDS = 300
MAX_PENDING = 16
MAX_BYTES = 64 * 1024 * 1024
CONSENT_WARNING = (
    "The token is a protocol guard, NOT proof of human consent. "
    "Show this exact preview to the user and obtain their specific approval before executing."
)


def action_error(code: str) -> ToolError:
    messages = {
        "INVALID_CONFIRMATION": "Invalid, expired, cancelled or already used confirmation token.",
        "ACTIONS_DISABLED": "The operator controls CASA_ALLOW_ACTIONS.",
        "MESSAGES_DISABLED": "The operator controls CASA_ALLOW_MESSAGES in addition to actions.",
        "UPLOADS_DISABLED": "The operator controls CASA_ALLOW_UPLOADS in addition to actions.",
        "UNVERIFIED_ACTIONS_DISABLED": (
            "The operator controls CASA_ALLOW_UNVERIFIED_ACTIONS in addition to actions."
        ),
        "CAPACITY_EXCEEDED": "Cancel pending previews or wait for their expiry.",
        "INVALID_FILE": "Choose a nonempty regular file within the upload policy.",
    }
    return ToolError(f"{code}: {messages[code]}")


@dataclass(frozen=True)
class PendingAction:
    home_id: str
    operation: str
    group: Group
    preview_json: str = field(repr=False)
    invoke: Invocation = field(repr=False)
    expires_at: float
    size_bytes: int = 0


class ActionStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._pending: dict[str, PendingAction] = {}
        # In-flight filesystem workers own reservations until actual completion,
        # even after their prepare request times out or is cancelled.
        self._snapshot_reservations: dict[object, int] = {}

    def purge(self) -> None:
        now = self._clock()
        self._pending = {k: v for k, v in self._pending.items() if v.expires_at > now}

    def check_capacity(self, additional_bytes: int = 0) -> None:
        self.purge()
        if (
            len(self._pending) + len(self._snapshot_reservations) >= MAX_PENDING
            or additional_bytes < 0
            or self.remaining_bytes() < additional_bytes
        ):
            raise action_error("CAPACITY_EXCEEDED")

    def remaining_bytes(self) -> int:
        self.purge()
        return (
            MAX_BYTES
            - sum(p.size_bytes for p in self._pending.values())
            - sum(self._snapshot_reservations.values())
        )

    def reserve_snapshot(self, size_bytes: int) -> object:
        if size_bytes <= 0:
            raise action_error("CAPACITY_EXCEEDED")
        self.check_capacity(size_bytes)
        reservation = object()
        self._snapshot_reservations[reservation] = size_bytes
        return reservation

    def release_snapshot(self, reservation: object) -> None:
        self._snapshot_reservations.pop(reservation, None)

    def add(
        self,
        home_id: str,
        operation: str,
        group: Group,
        preview: dict[str, JsonValue],
        invoke: Invocation,
        *,
        retained_bytes: int = 0,
        snapshot_reservation: object | None = None,
    ) -> dict[str, JsonValue]:
        preview_json = json.dumps(preview, ensure_ascii=False, sort_keys=True)
        preview_bytes = len(preview_json.encode("utf-8"))
        reserved_bytes = 0
        if snapshot_reservation is not None:
            reserved = self._snapshot_reservations.get(snapshot_reservation)
            if reserved is None or not 0 < retained_bytes <= reserved:
                raise action_error("CAPACITY_EXCEEDED")
            reserved_bytes = reserved
        # Check the delta while the existing reservation is still charged.
        self.purge()
        if (
            len(self._pending)
            + len(self._snapshot_reservations)
            - (1 if snapshot_reservation is not None else 0)
            >= MAX_PENDING
            or retained_bytes < 0
            or self.remaining_bytes() < preview_bytes + retained_bytes - reserved_bytes
        ):
            raise action_error("CAPACITY_EXCEEDED")
        token = secrets.token_urlsafe(32)
        if snapshot_reservation is not None:
            self.release_snapshot(snapshot_reservation)
        self._pending[token] = PendingAction(
            home_id,
            operation,
            group,
            preview_json,
            invoke,
            self._clock() + TTL_SECONDS,
            preview_bytes + retained_bytes,
        )
        return {
            "confirmation_token": token,
            "operation": operation,
            "home_id": home_id,
            "preview": preview,
            "expires_in_seconds": TTL_SECONDS,
            "warning": CONSENT_WARNING,
        }

    def get(self, token: str) -> PendingAction:
        self.purge()
        pending = self._pending.get(token)
        if pending is None:
            raise action_error("INVALID_CONFIRMATION")
        return pending

    def consume(self, token: str) -> PendingAction:
        self.get(token)
        return self._pending.pop(token)

    def clear(self) -> None:
        self._pending.clear()
