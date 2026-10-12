"""Shared prepare/execute machinery for every named action module."""

import asyncio
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from casahome.exceptions import CasaApiError
from mcp.server import MCPServer
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata, func_metadata
from mcp.types import ToolAnnotations
from pydantic import BaseModel, JsonValue, ValidationError

from ..errors import failure
from ..runtime import AppContext
from ..tools import resolve_home
from .models import CATALOG_REJECTION_WARNING, ActionResult
from .policy import ACTION_METHODS, UNVERIFIED_CONTRACT_WARNING, action_unverified
from .store import CONSENT_WARNING, Group, Invocation, action_error

PREPARE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
UPLOAD_PREPARE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)
EXECUTE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)
CANCEL = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)

F = TypeVar("F", bound=Callable[..., object])
M = TypeVar("M", bound=BaseModel)


class ActionToolDecorator(Protocol):
    def __call__(
        self, *, description: str, annotations: ToolAnnotations, structured_output: bool
    ) -> Callable[[F], F]: ...


def make_action_tool(server: MCPServer, validators: dict[str, FuncMetadata]) -> ActionToolDecorator:
    """Register a tool and keep its argument codec for the private input guard."""

    def action_tool(
        *, description: str, annotations: ToolAnnotations, structured_output: bool
    ) -> Callable[[F], F]:
        def register(fn: F) -> F:
            validators[fn.__name__] = func_metadata(fn, skip_names=("ctx",))
            server.add_tool(
                fn,
                description=description,
                annotations=annotations,
                structured_output=structured_output,
            )
            return fn

        return register

    return action_tool


def description(summary: str) -> str:
    return f"{summary} Prepare only, no account mutation. {CONSENT_WARNING}"


def authorize(app: AppContext, home_id: str | None, group: Group, operation: str) -> str:
    """Home, then operator flags, then credentials. No SDK access on any refusal."""
    home = resolve_home(app, home_id)
    if not app.settings.allow_actions:
        raise action_error("ACTIONS_DISABLED")
    if group == "messages" and not app.settings.allow_messages:
        raise action_error("MESSAGES_DISABLED")
    if group == "uploads" and not app.settings.allow_uploads:
        raise action_error("UPLOADS_DISABLED")
    if action_unverified(operation) and not app.settings.allow_unverified_actions:
        raise action_error("UNVERIFIED_ACTIONS_DISABLED")
    if app.settings.refresh_token is None or app.actions is None:
        raise failure("AUTH_NOT_CONFIGURED")
    return home


def result(home: str, operation: str) -> ActionResult:
    return ActionResult(outcome="SUCCEEDED", operation=operation, home_id=home)


def preview_body(body: BaseModel) -> dict[str, JsonValue]:
    # SDK codecs validate before preparation. JSON-mode is the exact immutable
    # payload used for preview and reconstructed for the one execution attempt.
    return body.model_dump(mode="json")


def build(model: type[M], data: dict[str, Any]) -> M:
    """Validate an SDK write body without letting Pydantic echo rejected values."""
    try:
        return model.model_validate(data)
    except ValidationError:
        pass
    raise failure("INVALID_ARGUMENT")


def prepare(
    app: AppContext,
    home_id: str | None,
    operation: str,
    preview: dict[str, JsonValue],
    invoke: Invocation,
    group: Group = "actions",
) -> dict[str, JsonValue]:
    if operation not in ACTION_METHODS:
        raise failure("INTERNAL_ERROR")
    home = authorize(app, home_id, group, operation)
    if action_unverified(operation):
        # Derived from the SDK marker, so no prepare can omit it.
        preview = {**preview, "contract_warning": UNVERIFIED_CONTRACT_WARNING}
    return app.action_store.add(home, operation, group, preview, invoke)


async def execute(app: AppContext, token: str, confirmed: bool) -> ActionResult:
    pending = app.action_store.get(token)
    if not confirmed:
        return ActionResult(
            outcome="NOT_EXECUTED",
            operation=pending.operation,
            home_id=pending.home_id,
        )
    authorize(app, pending.home_id, pending.group, pending.operation)
    api = app.actions
    if api is None:
        raise failure("AUTH_NOT_CONFIGURED")
    # No await before this atomic pop. Every attempt consumes the token before
    # waiting for a semaphore, refreshing auth or making ANY SDK call.
    pending = app.action_store.consume(token)
    try:
        async with asyncio.timeout(app.deadline_seconds), app.semaphore:
            return await pending.invoke(api, pending.home_id)
    except Exception as error:
        # Only this precise publish rejection is classified. It isn't evidence
        # that earlier server-side changes were completely rolled back.
        if (
            pending.operation in {"update_entity_model", "update_entity_make_model"}
            and isinstance(error, CasaApiError)
            and error.status == 400
            and error.code == "CATALOG_MODEL_UNVERIFIED"
        ):
            return ActionResult(
                outcome="REJECTED_UNKNOWN_PRODUCT",
                operation=pending.operation,
                home_id=pending.home_id,
                warning=CATALOG_REJECTION_WARNING,
            )
        # Even response parse failures can follow a completed write. No retries,
        # reusable token, raw exception text or raw upstream response.
        return ActionResult(
            outcome="UNKNOWN",
            operation=pending.operation,
            home_id=pending.home_id,
        )
