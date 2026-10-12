"""Finite provisional scalar prepares, with bounded read context for destructive changes."""

import re
from typing import Annotated, Literal

from casahome.models.documents import DocumentDetailsResponse, DocumentStructureSuggestionsResponse
from casahome.models.recovered_contracts import (
    DismissDocumentStructureSuggestionBody,
    UpdateRequestDetailBody,
    UpdateStoryBody,
    UpdateTaskScalarBody,
)
from mcp.server.mcpserver import Context
from pydantic import Field, JsonValue

from ..action_protocol import CasaActionsProtocol
from ..errors import failure
from ..runtime import AppContext
from ..safe_values import exact_safe_text
from ..tools import HomeId
from .core import (
    PREPARE,
    READ_PREPARE,
    ActionToolDecorator,
    build,
    prepare,
    prepare_from_read,
    result,
)
from .models import (
    NOT_APPLIED_WARNING,
    ActionResult,
    PathId,
)
from .store import Invocation
from .workflow_tools import gated_description

EditText = Annotated[str, Field(min_length=1, max_length=10_000, strict=True)]
EditName = Annotated[str, Field(min_length=1, max_length=256, strict=True)]
FloorNumber = Annotated[int, Field(ge=-1000, le=1000, strict=True)]
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def not_applied(home: str, operation: str) -> ActionResult:
    return ActionResult(
        outcome="NOT_APPLIED", operation=operation, home_id=home, warning=NOT_APPLIED_WARNING
    )


def suggestion_context(
    response: DocumentStructureSuggestionsResponse, suggestion_id: str
) -> tuple[list[str], dict[str, JsonValue]]:
    if not isinstance(response, DocumentStructureSuggestionsResponse):
        raise failure("SCHEMA_MISMATCH")
    if len(response.suggestions) > 100:
        raise failure("INVALID_ARGUMENT")
    matches = [item for item in response.suggestions if item.id == suggestion_id]
    if len(matches) != 1:
        raise failure("INVALID_ARGUMENT")
    item = matches[0]
    values = item.current_values
    if (
        item.state != "pending"
        or item.changed_since_analysis is not False
        or item.responded_at is not None
        or len(values) > 20
        or not all(exact_safe_text(value, maximum=10_000) for value in values)
        or not isinstance(item.entity_id, str)
        or not SAFE_ID.fullmatch(item.entity_id)
        or not isinstance(item.definition_id, str)
        or not SAFE_ID.fullmatch(item.definition_id)
        or not all(
            exact_safe_text(value, maximum=limit, nonblank=True)
            for value, limit in (
                (item.section, 128),
                (item.title, 256),
                (item.current_label, 256),
                (item.proposed_label, 256),
                (item.reason, 1000),
            )
        )
    ):
        raise failure("INVALID_ARGUMENT")
    return values, {
        "entity_id": item.entity_id,
        "definition_id": item.definition_id,
        "section": item.section,
        "title": item.title,
        "current_label": item.current_label,
        "proposed_label": item.proposed_label,
        "reason": item.reason,
        "state": item.state,
        "changed_since_analysis": item.changed_since_analysis,
        "responded_at": item.responded_at,
    }


STRUCTURE_RISK = (
    "State can change after preparation. expected_values may only guard current values. "
    "No second read at execution and no automatic retry or replacement."
)


def register_recovered_tools(action_tool: ActionToolDecorator) -> None:
    @action_tool(
        description=gated_description(
            "PATCH a request title and/or read state (read or unread). At least one is required. "
            "Read casa_get_request first. Omitted fields aren't sent. No explicit null clear.",
            "update_request_detail",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_request_detail(
        request_id: PathId,
        ctx: Context[AppContext],
        title: EditText | None = None,
        read_state: Literal["read", "unread"] | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(UpdateRequestDetailBody, {"title": title, "read_state": read_state})
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_request_detail(
                home, request_id, UpdateRequestDetailBody.model_validate_json(snapshot)
            )
            return result(home, "update_request_detail")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_request_detail",
            {"request_id": request_id, **body.model_dump(mode="json", exclude_none=True)},
            invoke,
            retained_bytes=len(snapshot.encode("utf-8")),
        )

    @action_tool(
        description=gated_description(
            "PATCH a caller-supplied task ID. Read casa_get_task_details first if available "
            "(requires UNVERIFIED_READS). No typed task lane is exposed. Edit title, description "
            "and/or emoji scalars only, no attachment changes or explicit null clears.",
            "update_task",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_task(
        task_id: PathId,
        ctx: Context[AppContext],
        title: EditText | None = None,
        description: EditText | None = None,
        emoji: EditText | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            UpdateTaskScalarBody,
            {"title": title, "description": description, "emoji": emoji},
        )
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_task(home, task_id, UpdateTaskScalarBody.model_validate_json(snapshot))
            return result(home, "update_task")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_task",
            {"task_id": task_id, **body.model_dump(mode="json", exclude_none=True)},
            invoke,
            retained_bytes=len(snapshot.encode("utf-8")),
        )

    @action_tool(
        description=gated_description(
            "PATCH a story's name and/or floor_number. At least one is required. "
            "Read casa_list_inventory kind=stories first. Local floor bound is not a Casa "
            "limit. No explicit null clear or sorting guarantee. Message response can't prove "
            "application.",
            "update_story",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_story(
        story_id: PathId,
        ctx: Context[AppContext],
        name: EditName | None = None,
        floor_number: FloorNumber | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(UpdateStoryBody, {"name": name, "floor_number": floor_number})
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_story(home, story_id, UpdateStoryBody.model_validate_json(snapshot))
            return ActionResult(
                outcome="UNKNOWN",
                operation="update_story",
                home_id=home,
                warning="Message response doesn't prove application. Reconcile the story before "
                "any new attempt. Never automatically retry.",
            )

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_story",
            {"story_id": story_id, **body.model_dump(mode="json", exclude_none=True)},
            invoke,
            retained_bytes=len(snapshot.encode("utf-8")),
        )

    @action_tool(
        description=gated_description(
            "Dismiss one document structure suggestion. Preparation performs one single-attempt "
            "Casa request, checks complete exact context and exact safe current values. "
            "No account mutation during preparation or second read at execution. "
            "State can change; expected_values may only guard current values. "
            "saved=false is NOT_APPLIED, doesn't prove rollback. Reconcile before any new "
            "attempt. Never automatically retry or prepare a replacement.",
            "dismiss_document_structure_suggestion",
        ),
        annotations=READ_PREPARE,
        structured_output=True,
    )
    async def casa_prepare_dismiss_document_structure_suggestion(
        document_id: PathId,
        suggestion_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        app = ctx.request_context.lifespan_context

        def finalize(
            home: str, response: DocumentStructureSuggestionsResponse
        ) -> tuple[dict[str, JsonValue], Invocation, int]:
            values, context = suggestion_context(response, suggestion_id)
            body = build(DismissDocumentStructureSuggestionBody, {"expected_values": values})
            snapshot = body.model_dump_json()

            async def invoke(api: CasaActionsProtocol, selected: str) -> ActionResult:
                validated = DismissDocumentStructureSuggestionBody.model_validate_json(snapshot)
                saved = await api.dismiss_document_structure_suggestion(
                    selected, document_id, suggestion_id, validated.expected_values
                )
                return (
                    result(selected, "dismiss_document_structure_suggestion")
                    if saved.saved
                    else not_applied(selected, "dismiss_document_structure_suggestion")
                )

            return (
                {
                    "document_id": document_id,
                    "suggestion_id": suggestion_id,
                    **body.model_dump(mode="json"),
                    "suggestion_context": context,
                    "risk": STRUCTURE_RISK,
                },
                invoke,
                len(snapshot.encode("utf-8")),
            )

        return await prepare_from_read(
            app,
            home_id,
            "dismiss_document_structure_suggestion",
            lambda reads, home: reads.document_structure_suggestions(
                home, document_id, retry_on_401=False
            ),
            finalize,
        )

    @action_tool(
        description=gated_description(
            "Permanently delete one document. Related work and storage cleanup are unknown. "
            "No automatic cleanup or undo. Preparation performs one bounded Casa document detail "
            "single-attempt request and requires complete exact safe identifying metadata. "
            "No account mutation during preparation. "
            "State can change between read and execution; no revision guard exists. "
            "deleted=false is NOT_APPLIED, doesn't prove rollback. "
            "Reconcile before any new attempt. Never automatically retry or prepare a replacement.",
            "delete_document",
        ),
        annotations=READ_PREPARE,
        structured_output=True,
    )
    async def casa_prepare_delete_document(
        document_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        app = ctx.request_context.lifespan_context

        def finalize(home: str, details: object) -> tuple[dict[str, JsonValue], Invocation, int]:
            if not isinstance(details, DocumentDetailsResponse):
                raise failure("SCHEMA_MISMATCH")
            document = details.document
            optional = (
                (document.document_type, 256),
                (document.document_date, 64),
                (document.organization.status if document.organization else None, 256),
                (document.extraction.status if document.extraction else None, 256),
            )
            if (
                document.id != document_id
                or not SAFE_ID.fullmatch(document_id)
                or not exact_safe_text(document.name, maximum=256, nonblank=True)
                or any(
                    value is not None and not exact_safe_text(value, maximum=limit)
                    for value, limit in optional
                )
                or (
                    document.size_bytes is not None
                    and (type(document.size_bytes) is not int or document.size_bytes < 0)
                )
            ):
                raise failure("INVALID_ARGUMENT")
            metadata: dict[str, JsonValue] = {
                "id": document_id,
                "name": document.name,
            }
            for key in ("document_type", "document_date", "size_bytes"):
                if key in document.model_fields_set:
                    metadata[key] = getattr(document, key)
            for key in ("organization", "extraction"):
                if key in document.model_fields_set:
                    job = getattr(document, key)
                    if job is None:
                        metadata[f"{key}_status"] = None
                    elif "status" in job.model_fields_set:
                        metadata[f"{key}_status"] = job.status

            async def invoke(api: CasaActionsProtocol, selected: str) -> ActionResult:
                response = await api.delete_document(selected, document_id)
                return (
                    result(selected, "delete_document")
                    if response.deleted
                    else not_applied(selected, "delete_document")
                )

            return (
                {
                    "document_id": document_id,
                    "read_metadata": metadata,
                    "document_metadata_complete": True,
                    "risk": "Permanent deletion. Related work and "
                    "storage cleanup unknown. State can change after read. "
                    "No revision guard or undo.",
                },
                invoke,
                0,
            )

        return await prepare_from_read(
            app,
            home_id,
            "delete_document",
            lambda reads, home: reads.document_details(home, document_id, retry_on_401=False),
            finalize,
        )
