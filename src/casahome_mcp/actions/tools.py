"""Explicit named prepares. Each owns a typed SDK invocation, not generic dispatch."""

import asyncio
import hashlib
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from casahome.models.documents import DocumentStructureSuggestionsResponse
from casahome.models.entity_publish import SaveAndPublishEntityRequest
from casahome.models.mail_workflows import AddMailboxRecipientRequest, MailboxAutoArchiveRequest
from casahome.models.verified_writes import (
    AnswerTodoQuestionRequest,
    CasaAIMessageInput,
    DocumentUploadFile,
    MaterializeTodoRequest,
    RateCasaAIMessageRequest,
    RespondToDocumentStructureSuggestionRequest,
    RespondToSuggestedTodoRequest,
    SendCasaAIMessageRequest,
    SubmitQuestionRoundRequest,
    UpdateAutopilotPlanRequest,
    UpdateNotificationSettingsRequest,
)
from casahome.models.write_contracts import CreateTodoBody, SendRequestMessageRequest
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from pydantic import Field, JsonValue

from ..action_protocol import CasaActionsProtocol
from ..errors import failure
from ..runtime import AppContext
from ..tools import EntityId, HomeId
from .core import (
    CANCEL,
    EXECUTE,
    PREPARE,
    READ_PREPARE,
    UPLOAD_PREPARE,
    authorize,
    build,
    description,
    execute,
    make_action_tool,
    prepare,
    prepare_from_read,
    preview_body,
    result,
)
from .inventory_tools import CATALOG_MATCH_RISK, register_inventory_tools
from .models import (
    ActionResult,
    Answer,
    Content,
    MailboxArchiveDays,
    Notifications,
    PathId,
    RecipientName,
    RoundAnswers,
    StrictFlag,
    Token,
)
from .policy import ACTION_METHODS, ACTION_TOOLS
from .recovered_tools import (
    STRUCTURE_RISK,
    not_applied,
    register_recovered_tools,
    suggestion_context,
)
from .store import Invocation, action_error
from .uploads import LOCAL_FILE_CAP, SnapshotWorker, snapshot_file
from .workflow_tools import register_workflow_tools

__all__ = ["ACTION_METHODS", "ACTION_TOOLS", "execute", "register_action_tools"]


def check_upload_deadline(app: AppContext, deadline: float) -> None:
    if app.uploads_closed or asyncio.get_running_loop().time() >= deadline:
        raise failure("TIMEOUT")


async def prepare_upload_document(
    app: AppContext,
    file_path: str,
    filename: str,
    mimetype: str,
    find_todos: bool,
    home_id: str | None = None,
) -> dict[str, JsonValue]:
    """One monotonic deadline, with leases surviving cancellation of this coroutine."""
    deadline = asyncio.get_running_loop().time() + app.deadline_seconds
    home = authorize(app, home_id, "uploads", "upload_document")
    if app.api is None:
        raise failure("AUTH_NOT_CONFIGURED")
    # Only the chosen basename reaches Casa, never the local source path.
    basename = Path(filename).name
    if not basename or basename in {".", ".."}:
        raise action_error("INVALID_FILE")
    lock_owned = False
    worker: SnapshotWorker | None = None
    try:
        async with asyncio.timeout_at(deadline):
            check_upload_deadline(app, deadline)
            await app.upload_lock.acquire()
            lock_owned = True
            check_upload_deadline(app, deadline)
            authorize(app, home, "uploads", "upload_document")
            app.action_store.check_capacity()
            async with app.semaphore:
                policy = await app.api.document_types(home)
            if mimetype not in policy.allowed_mimetypes or policy.max_files_per_upload < 1:
                raise action_error("INVALID_FILE")
            check_upload_deadline(app, deadline)
            authorize(app, home, "uploads", "upload_document")
            limit = min(
                LOCAL_FILE_CAP, policy.max_file_size_bytes, app.action_store.remaining_bytes()
            )
            worker = SnapshotWorker(
                app.action_store,
                app.upload_lock,
                app.upload_workers,
                file_path,
                limit,
                snapshot_file,
            )
            # Worker now owns lock/capacity. Cancellation of this request doesn't
            # release either while the filesystem worker is still allocating.
            lock_owned = False
            content = await worker.content()
            DocumentUploadFile(size_bytes=len(content), mimetype=mimetype)
            check_upload_deadline(app, deadline)
            authorize(app, home, "uploads", "upload_document")

            async def invoke(api: CasaActionsProtocol, selected_home: str) -> ActionResult:
                await api.upload_document(
                    selected_home, content, basename, mimetype, find_todos=find_todos
                )
                return result(selected_home, "upload_document")

            preview: dict[str, JsonValue] = {
                "basename": basename,
                "mimetype": mimetype,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "find_todos": find_todos,
                "risk": "Uploads bytes to Casa storage, creates a home document and may "
                "generate suggested todos. Partial upload steps aren't undone on failure.",
            }
            # Hashing is synchronous. An overdue event-loop turn can't mint a
            # late token even if the timeout callback hasn't run yet.
            check_upload_deadline(app, deadline)
            return app.action_store.add(
                home,
                "upload_document",
                "uploads",
                preview,
                invoke,
                retained_bytes=len(content),
                snapshot_reservation=worker.reservation,
            )
    except TimeoutError:
        raise failure("TIMEOUT") from None
    except ToolError:
        raise
    except Exception:
        raise action_error("INVALID_FILE") from None
    finally:
        # No await. A second cancellation can't interrupt abandonment and free
        # capacity while the filesystem worker is still allocating.
        if worker is not None:
            worker.abandon()
        elif lock_owned:
            app.upload_lock.release()


def register_action_tools(server: MCPServer) -> dict[str, FuncMetadata]:
    validators: dict[str, FuncMetadata] = {}
    action_tool = make_action_tool(server, validators)
    register_workflow_tools(action_tool)
    register_inventory_tools(action_tool)
    register_recovered_tools(action_tool)

    @action_tool(
        description=description(
            "Add a mailbox recipient using explicit first and last names only. "
            "No business name, kind or primary flags. May change account mail handling. "
            "Requires ACTIONS only."
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_add_mailbox_recipient(
        first_name: RecipientName,
        last_name: RecipientName,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = AddMailboxRecipientRequest(first_name=first_name, last_name=last_name)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.add_mailbox_recipient(home, first_name=first_name, last_name=last_name)
            return result(home, "add_mailbox_recipient")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "add_mailbox_recipient",
            {
                **body.model_dump(mode="json", exclude_none=True),
                "risk": "Adding a recipient may change account mail handling.",
            },
            invoke,
        )

    @action_tool(
        description=description(
            "Update mailbox auto-archive using only the observed 30 or explicit null. "
            "Retention and disposal behavior is UNVERIFIED. Neither value guarantees no effect. "
            "Requires ACTIONS only."
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_mailbox_auto_archive(
        mailbox_auto_archive_days: MailboxArchiveDays,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = MailboxAutoArchiveRequest(mailbox_auto_archive_days=mailbox_auto_archive_days)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            response = await api.update_mailbox_auto_archive(home, mailbox_auto_archive_days)
            if not response.success:
                raise ValueError("Unconfirmed action outcome")
            return result(home, "update_mailbox_auto_archive")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_mailbox_auto_archive",
            {
                **preview_body(body),
                "risk": "Retention and disposal behavior is UNVERIFIED. "
                "Neither 30 nor null guarantees no effect.",
            },
            invoke,
        )

    @action_tool(
        description=description("Move an entity to a room, replacing its room."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_move_entity_to_room(
        entity_id: EntityId,
        room_id: EntityId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.move_entity_to_room(home, entity_id, room_id)
            return result(home, "move_entity_to_room")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "move_entity_to_room",
            {"entity_id": entity_id, "room_id": room_id},
            invoke,
        )

    @action_tool(
        description=description("Rate an AI message good or bad. No clear variant."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_rate_ai_message(
        message_id: PathId,
        rating: Literal["good", "bad"],
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = RateCasaAIMessageRequest(rating=rating)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            response = await api.rate_ai_message(home, message_id, rating)
            if not response.success:
                raise ValueError("Unconfirmed action outcome")
            return result(home, "rate_ai_message")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "rate_ai_message",
            {"message_id": message_id, **preview_body(body)},
            invoke,
        )

    @action_tool(
        description=description("Accept a suggested todo. Declining isn't verified."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_respond_to_suggested_todo(
        suggestion_id: PathId,
        decision: Literal["accept"],
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = RespondToSuggestedTodoRequest(decision=decision)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.respond_to_suggested_todo(home, suggestion_id, decision)
            return result(home, "respond_to_suggested_todo")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "respond_to_suggested_todo",
            {"suggestion_id": suggestion_id, **preview_body(body)},
            invoke,
        )

    @action_tool(
        description=description("Convert a todo into a concierge request."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_send_todo_to_concierge(
        todo_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = MaterializeTodoRequest(destination="concierge")

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.send_todo_to_concierge(home, todo_id)
            return result(home, "send_todo_to_concierge")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "send_todo_to_concierge",
            {"todo_id": todo_id, **preview_body(body)},
            invoke,
        )

    @action_tool(
        description=description("Save a single or multi-select answer. No skip variant."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_answer_todo_question(
        todo_id: PathId,
        round_id: PathId,
        question_id: PathId,
        answer: Answer,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        skip: Literal[False] = False,
    ) -> dict[str, JsonValue]:
        body = AnswerTodoQuestionRequest.model_validate(
            {"is_skipped": skip, "answer": answer.model_dump()}
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = AnswerTodoQuestionRequest.model_validate_json(snapshot)
            await api.answer_todo_question(
                home, todo_id, round_id, question_id, answer=validated.answer, skip=False
            )
            return result(home, "answer_todo_question")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "answer_todo_question",
            {
                "todo_id": todo_id,
                "round_id": round_id,
                "question_id": question_id,
                **preview_body(body),
            },
            invoke,
        )

    @action_tool(
        description=description("Submit a question round with explicit answers."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_submit_todo_question_round(
        todo_id: PathId,
        round_id: PathId,
        answers: RoundAnswers,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = SubmitQuestionRoundRequest.model_validate(
            {"answers": [answer.model_dump() for answer in answers]}
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = SubmitQuestionRoundRequest.model_validate_json(snapshot)
            await api.submit_todo_question_round(home, todo_id, round_id, validated.answers)
            return result(home, "submit_todo_question_round")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "submit_todo_question_round",
            {"todo_id": todo_id, "round_id": round_id, **preview_body(body)},
            invoke,
        )

    @action_tool(
        description=description(
            "Update a plan using observed every_quarter cadence and empty association map. "
            "Empty-map preservation semantics are UNVERIFIED. Future services may cost money."
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_autopilot_plan(
        plan_id: PathId,
        enabled: StrictFlag,
        next_desired_occurrence_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        selected_cadence: Literal["every_quarter"],
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        try:
            occurrence = date.fromisoformat(next_desired_occurrence_date)
        except ValueError:
            raise failure("INVALID_ARGUMENT") from None
        body = UpdateAutopilotPlanRequest(
            enabled=enabled,
            selected_cadence=selected_cadence,
            next_desired_occurrence_date=occurrence,
            associations_enabled_map={},
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = UpdateAutopilotPlanRequest.model_validate_json(snapshot)
            await api.update_autopilot_plan(
                home,
                plan_id,
                enabled=validated.enabled,
                selected_cadence=validated.selected_cadence,
                next_desired_occurrence_date=validated.next_desired_occurrence_date,
                associations_enabled_map=validated.associations_enabled_map,
            )
            return result(home, "update_autopilot_plan")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_autopilot_plan",
            {
                "plan_id": plan_id,
                **preview_body(body),
                "risk": "May affect paid future services. Empty-map semantics unknown.",
            },
            invoke,
        )

    @action_tool(
        description=description("Toggle explicit notification type/push pairs only."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_notification_settings(
        settings: Notifications,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = UpdateNotificationSettingsRequest.model_validate(
            {"settings": [setting.model_dump() for setting in settings]}
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = UpdateNotificationSettingsRequest.model_validate_json(snapshot)
            await api.update_notification_settings(home, validated.settings)
            return result(home, "update_notification_settings")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_notification_settings",
            preview_body(body),
            invoke,
        )

    @action_tool(
        description=description("Send text to Casa AI. Requires ACTIONS and MESSAGES."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_send_ai_message(
        text: Content,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = SendCasaAIMessageRequest(input=CasaAIMessageInput(text=text, upload_ids=[]))

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.send_ai_message(home, text)
            return result(home, "send_ai_message")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "send_ai_message",
            preview_body(body),
            invoke,
            "messages",
        )

    @action_tool(
        description=description(
            "Send one member request-thread text, no attachments. Requires ACTIONS and MESSAGES."
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_send_request_message(
        request_id: PathId,
        content: Content,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = SendRequestMessageRequest(sender_role="member", content=content)
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.send_request_message(
                home, request_id, SendRequestMessageRequest.model_validate_json(snapshot)
            )
            return result(home, "send_request_message")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "send_request_message",
            {"request_id": request_id, **body.model_dump(mode="json", exclude_none=True)},
            invoke,
            "messages",
        )

    @action_tool(
        description=description(
            "Create a text-only todo. Never automatically confirm support or attach files."
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_create_todo_result(
        content: Content,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = CreateTodoBody(content=content)
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            response = await api.create_todo_result(
                home, CreateTodoBody.model_validate_json(snapshot)
            )
            return ActionResult(
                outcome="SUCCEEDED",
                operation="create_todo_result",
                home_id=home,
                needs_support_confirmation=response.needs_support_confirmation,
            )

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "create_todo_result",
            body.model_dump(mode="json", exclude_none=True),
            invoke,
        )

    @action_tool(
        description=description("Delete one todo permanently. No related-work cleanup or undo."),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_delete_todo(
        todo_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.delete_todo(home, todo_id)
            return result(home, "delete_todo")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "delete_todo",
            {"todo_id": todo_id, "risk": "Permanent deletion. No undo."},
            invoke,
        )

    @action_tool(
        description=description(
            "Publish model.name with empty props. "
            "No make/catalog IDs, properties or clear semantics. " + CATALOG_MATCH_RISK
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_entity_model(
        entity_id: EntityId,
        model_name: Content,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(SaveAndPublishEntityRequest, {"model": {"name": model_name}, "props": []})

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_entity_model(home, entity_id, model_name)
            return result(home, "update_entity_model")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_entity_model",
            {
                "entity_id": entity_id,
                **body.model_dump(mode="json", exclude_none=True),
                "risk": CATALOG_MATCH_RISK,
            },
            invoke,
        )

    @action_tool(
        description=description(
            "Accept a document structure suggestion. Preparation performs one single-attempt Casa "
            "request and checks complete exact context and exact safe current values. State can "
            "change and expected_values may only guard current values. "
            "No account mutation during preparation, no second read during execution and no "
            "automatic conflict retry or replacement. saved=false is NOT_APPLIED."
        ),
        annotations=READ_PREPARE,
        structured_output=True,
    )
    async def casa_prepare_respond_to_document_structure_suggestion(
        document_id: PathId,
        suggestion_id: PathId,
        ctx: Context[AppContext],
        decision: Literal["accepted"] = "accepted",
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        app = ctx.request_context.lifespan_context

        def finalize(
            home: str, response: DocumentStructureSuggestionsResponse
        ) -> tuple[dict[str, JsonValue], Invocation, int]:
            values, context = suggestion_context(response, suggestion_id)
            body = RespondToDocumentStructureSuggestionRequest(
                decision=decision, expected_values=values
            )
            snapshot = body.model_dump_json()

            async def invoke(api: CasaActionsProtocol, selected: str) -> ActionResult:
                validated = RespondToDocumentStructureSuggestionRequest.model_validate_json(
                    snapshot
                )
                saved = await api.respond_to_document_structure_suggestion(
                    selected,
                    document_id,
                    suggestion_id,
                    validated.expected_values,
                    decision=validated.decision,
                )
                if not saved.saved:
                    return not_applied(selected, "respond_to_document_structure_suggestion")
                return result(selected, "respond_to_document_structure_suggestion")

            return (
                {
                    "document_id": document_id,
                    "suggestion_id": suggestion_id,
                    **preview_body(body),
                    "suggestion_context": context,
                    "risk": STRUCTURE_RISK,
                },
                invoke,
                len(snapshot.encode("utf-8")),
            )

        return await prepare_from_read(
            app,
            home_id,
            "respond_to_document_structure_suggestion",
            lambda reads, home: reads.document_structure_suggestions(
                home, document_id, retry_on_401=False
            ),
            finalize,
        )

    @action_tool(
        description=description(
            "Snapshot one explicit regular local file, anywhere the process can read. "
            "Reads bytes and Casa document_types GET, no write. Symlinks to regular files allowed. "
            "Requires ACTIONS and UPLOADS. Execution creates a document and may generate todos."
        ),
        annotations=UPLOAD_PREPARE,
        structured_output=True,
    )
    async def casa_prepare_upload_document(
        file_path: Annotated[str, Field(min_length=1, max_length=4096, strict=True)],
        filename: Annotated[str, Field(min_length=1, max_length=1024, strict=True)],
        mimetype: Annotated[str, Field(min_length=1, max_length=128, strict=True)],
        find_todos: StrictFlag,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        return await prepare_upload_document(
            ctx.request_context.lifespan_context,
            file_path,
            filename,
            mimetype,
            find_todos,
            home_id,
        )

    @action_tool(
        description=(
            "Execute one prepared action once. Show the exact preview and obtain specific "
            "user approval first. confirmed=True isn't proof of consent. Operator gates and "
            "home allowlist are rechecked. False makes zero calls and preserves the token. "
            "UNKNOWN means the action may have happened. NOT_APPLIED (a false saved/deleted "
            "result) and REJECTED_UNKNOWN_PRODUCT don't prove complete rollback. "
            "Reconcile before any new retry. "
            "Never automatically retry or prepare a replacement."
        ),
        annotations=EXECUTE,
        structured_output=True,
    )
    async def casa_execute_action(
        confirmation_token: Token,
        confirmed: StrictFlag,
        ctx: Context[AppContext],
    ) -> ActionResult:
        return await execute(ctx.request_context.lifespan_context, confirmation_token, confirmed)

    @action_tool(
        description=(
            "Cancel a pending preview locally, consuming its token and releasing snapshot bytes. "
            "No account side effects. Invalid, expired and used tokens have one private error."
        ),
        annotations=CANCEL,
        structured_output=True,
    )
    async def casa_cancel_action(
        confirmation_token: Token,
        ctx: Context[AppContext],
    ) -> ActionResult:
        pending = ctx.request_context.lifespan_context.action_store.consume(confirmation_token)
        return ActionResult(
            outcome="CANCELLED", operation=pending.operation, home_id=pending.home_id
        )

    return validators
