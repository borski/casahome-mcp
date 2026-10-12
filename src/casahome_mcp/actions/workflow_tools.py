"""Named prepares for SDK workflow, mail, package, inventory and settings writes.

Most of these SDK methods carry the unverified marker. Their prepares require
CASA_ALLOW_UNVERIFIED_ACTIONS in addition to CASA_ALLOW_ACTIONS, and their
previews carry the UNVERIFIED_CONTRACT warning. Both derive from the SDK marker
at call time, never from a list here. Each tool owns one explicit SDK call.
"""

import re
from typing import Annotated, Literal

from casahome.models.mail_workflows import (
    AddPackageRequest,
    CreateEntityRequest,
    CreateLightingRequest,
    CreatePaintFromLibraryRequest,
    TrackingNumberValidationRequest,
    UpdatePackageAutoArchiveRequest,
    UpdatePackageRequest,
)
from casahome.models.verified_writes import UpdateAccessPreferencesRequest
from casahome.models.workflows import (
    AnalyzeDocumentRequest,
    ConfirmTodoSupportRequest,
    RejectSuggestedTodoRequest,
    ReorderTodoSectionRequest,
    UpdateAvailabilitySlotsRequest,
    UpdateDocumentBody,
    UpdateSchedulePreferencesRequest,
    UpdateTodoBody,
)
from casahome.models.write_contracts import UpdateEntityPropertiesRequest
from mcp.server.mcpserver import Context
from pydantic import Field, JsonValue

from ..action_protocol import CasaActionsProtocol
from ..errors import failure
from ..runtime import AppContext
from ..tools import EntityId, HomeId, resolve_home
from .core import PREPARE, ActionToolDecorator, build, description, prepare, result
from .models import (
    ActionResult,
    CatalogNumber,
    Content,
    DaysOfWeek,
    DocumentDate,
    Emoji,
    Label,
    OptionalIds,
    OrderedIds,
    PackageArchiveDays,
    PackageDirection,
    PathId,
    PropertyUpdates,
    Revision,
    SlotWindows,
    StrictFlag,
    TrackingNumber,
)
from .policy import UNVERIFIED_CONTRACT_WARNING, action_unverified

RoomIds = Annotated[list[EntityId], Field(min_length=1, max_length=100)]
SAFE_CARRIER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MAX_CARRIER_IDS = 20


def gated_description(summary: str, operation: str) -> str:
    """Gate text follows the SDK marker, so promotion updates descriptions too."""
    if action_unverified(operation):
        gate = f"Requires ACTIONS and UNVERIFIED_ACTIONS. {UNVERIFIED_CONTRACT_WARNING}"
    else:
        gate = "Requires ACTIONS only."
    return description(f"{summary} {gate}")


def unconfirmed() -> ValueError:
    return ValueError("Unconfirmed action outcome")


def register_workflow_tools(action_tool: ActionToolDecorator) -> None:
    # Todos -----------------------------------------------------------------

    @action_tool(
        description=gated_description(
            "Edit a todo's title, prepared brief or emoji. Supply at least one. "
            "Omitted fields are left out of the PATCH. No attachment changes.",
            "update_todo",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_todo(
        todo_id: PathId,
        ctx: Context[AppContext],
        title: Label | None = None,
        prepared_brief: Content | None = None,
        emoji: Emoji | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        if title is None and prepared_brief is None and emoji is None:
            raise failure("INVALID_ARGUMENT")
        body = build(
            UpdateTodoBody, {"title": title, "prepared_brief": prepared_brief, "emoji": emoji}
        )
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_todo(home, todo_id, UpdateTodoBody.model_validate_json(snapshot))
            return result(home, "update_todo")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_todo",
            {"todo_id": todo_id, **body.model_dump(mode="json", exclude_none=True)},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Reject a suggested todo with an optional dismissed or already_handled reason.",
            "reject_suggested_todo",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_reject_suggested_todo(
        suggestion_id: PathId,
        ctx: Context[AppContext],
        reason: Literal["dismissed", "already_handled"] | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(RejectSuggestedTodoRequest, {"reason": reason})

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.reject_suggested_todo(home, suggestion_id, reason)
            return result(home, "reject_suggested_todo")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "reject_suggested_todo",
            {"suggestion_id": suggestion_id, **body.model_dump(mode="json", exclude_none=True)},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Send an explicit support-question decision for a todo. No inferred default.",
            "confirm_todo_support",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_confirm_todo_support(
        todo_id: PathId,
        is_support_question: StrictFlag,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(ConfirmTodoSupportRequest, {"is_support_question": is_support_question})

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.confirm_todo_support(home, todo_id, is_support_question)
            return result(home, "confirm_todo_support")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "confirm_todo_support",
            {"todo_id": todo_id, **body.model_dump(mode="json")},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Ask Casa to retry todo preparation once with a bodyless POST. "
            "May start new preparation work.",
            "retry_todo",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_retry_todo(
        todo_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.retry_todo(home, todo_id)
            return result(home, "retry_todo")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "retry_todo",
            {"todo_id": todo_id, "risk": "May create new preparation or question rounds."},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Reorder one todo section with an explicit revision guard and full ordered IDs. "
            "Never refetches or resubmits a stale list.",
            "reorder_todo_section",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_reorder_todo_section(
        section: Literal["ready_for_scheduling", "send_to_concierge"],
        expected_revision: Revision,
        ordered_item_ids: OrderedIds,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            ReorderTodoSectionRequest,
            {"expected_revision": expected_revision, "ordered_item_ids": ordered_item_ids},
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = ReorderTodoSectionRequest.model_validate_json(snapshot)
            await api.reorder_todo_section(
                home,
                section,
                expected_revision=validated.expected_revision,
                ordered_item_ids=validated.ordered_item_ids,
            )
            return result(home, "reorder_todo_section")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "reorder_todo_section",
            {"section": section, **body.model_dump(mode="json")},
            invoke,
        )

    # Documents -------------------------------------------------------------

    @action_tool(
        description=gated_description(
            "Rename a document, set its type or date, or clear its date with "
            "clear_document_date=true. Read casa_get_document_details first. "
            "Supply at least one change.",
            "update_document",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_document(
        document_id: PathId,
        ctx: Context[AppContext],
        name: Label | None = None,
        document_type: PathId | None = None,
        document_date: DocumentDate | None = None,
        clear_document_date: StrictFlag = False,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        if clear_document_date and document_date is not None:
            raise failure("INVALID_ARGUMENT")
        fields: dict[str, object] = {
            key: value
            for key, value in {"name": name, "document_type": document_type}.items()
            if value is not None
        }
        if document_date is not None or clear_document_date:
            # Explicit null only on request. Unset never silently clears a date.
            fields["document_date"] = document_date
        if not fields:
            raise failure("INVALID_ARGUMENT")
        body = build(UpdateDocumentBody, fields)
        snapshot = body.model_dump_json(exclude_unset=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_document(
                home, document_id, UpdateDocumentBody.model_validate_json(snapshot)
            )
            return result(home, "update_document")

        preview: dict[str, JsonValue] = {
            "document_id": document_id,
            **body.model_dump(mode="json", exclude_unset=True),
        }
        if clear_document_date:
            preview["risk"] = "Sends document_date=null. Clearing semantics are unknown."
        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_document",
            preview,
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Read casa_get_document_details first. Start document analysis with an explicit "
            "reanalyze flag. No polling.",
            "analyze_document",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_analyze_document(
        document_id: PathId,
        reanalyze: StrictFlag,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(AnalyzeDocumentRequest, {"reanalyze": reanalyze})

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.analyze_document(home, document_id, reanalyze)
            return result(home, "analyze_document")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "analyze_document",
            {
                "document_id": document_id,
                **body.model_dump(mode="json"),
                "risk": "May replace earlier analysis and generate suggestions or todos.",
            },
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Read casa_get_document_details first. Start document organization with a bodyless "
            "POST. No polling.",
            "organize_document",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_organize_document(
        document_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.organize_document(home, document_id)
            return result(home, "organize_document")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "organize_document",
            {"document_id": document_id, "risk": "Starts background work on the document."},
            invoke,
        )

    # Scheduling ------------------------------------------------------------

    @action_tool(
        description=gated_description(
            "Replace scheduling day and time-window selections. Both lists are required "
            "and sent as given, including []. Use values from casa_get_schedule_preferences.",
            "update_schedule_preferences",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_schedule_preferences(
        selected_days_of_week: DaysOfWeek,
        selected_times_of_day: OptionalIds,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            UpdateSchedulePreferencesRequest,
            {
                "selected_days_of_week": selected_days_of_week,
                "selected_times_of_day": selected_times_of_day,
            },
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_schedule_preferences(
                home, UpdateSchedulePreferencesRequest.model_validate_json(snapshot)
            )
            return result(home, "update_schedule_preferences")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_schedule_preferences",
            {
                **body.model_dump(mode="json"),
                "risk": "Replaces both selections. Weekday numbering is unknown.",
            },
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Replace an availability request's integer slot windows. One compiled editor uses "
            "integer Unix seconds. Server units and semantics remain UNVERIFIED. "
            "[] is sent as []. May also submit the availability.",
            "update_availability_slots",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_availability_slots(
        availability_request_id: PathId,
        windows: SlotWindows,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            UpdateAvailabilitySlotsRequest, {"slots": [window.model_dump() for window in windows]}
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = UpdateAvailabilitySlotsRequest.model_validate_json(snapshot)
            await api.update_availability_slots(home, availability_request_id, validated.slots)
            return result(home, "update_availability_slots")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_availability_slots",
            {
                "availability_request_id": availability_request_id,
                **body.model_dump(mode="json"),
                "risk": "Replaces slots and may finalize submission. One compiled editor uses "
                "integer Unix seconds. Server units and semantics remain UNVERIFIED.",
            },
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Cancel one vendor visit. May incur cancellation fees. Not undoable.",
            "cancel_vendor_visit",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_cancel_vendor_visit(
        visit_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.cancel_vendor_visit(home, visit_id)
            return result(home, "cancel_vendor_visit")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "cancel_vendor_visit",
            {
                "visit_id": visit_id,
                "risk": "May incur cancellation fees and maintenance side effects. "
                "Cancellation is not undoable.",
            },
            invoke,
        )

    # Mail ------------------------------------------------------------------

    @action_tool(
        description=gated_description(
            "Remove one mailbox recipient. Restrictions and undo are unknown.",
            "remove_mailbox_recipient",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_remove_mailbox_recipient(
        recipient_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.remove_mailbox_recipient(home, recipient_id)
            return result(home, "remove_mailbox_recipient")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "remove_mailbox_recipient",
            {
                "recipient_id": recipient_id,
                "risk": "May change account mail handling. No known undo.",
            },
            invoke,
        )

    @action_tool(
        description=gated_description("Mark one mail item read.", "mark_mail_item_read"),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_mark_mail_item_read(
        mail_item_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.mark_mail_item_read(home, mail_item_id)
            return result(home, "mark_mail_item_read")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "mark_mail_item_read",
            {"mail_item_id": mail_item_id},
            invoke,
        )

    @action_tool(
        description=gated_description("Mark one mail item unread.", "mark_mail_item_unread"),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_mark_mail_item_unread(
        mail_item_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.mark_mail_item_unread(home, mail_item_id)
            return result(home, "mark_mail_item_unread")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "mark_mail_item_unread",
            {"mail_item_id": mail_item_id},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Archive (true) or unarchive (false) one mail item. Archive isn't shredding.",
            "set_mail_item_archived",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_set_mail_item_archived(
        mail_item_id: PathId,
        archived: StrictFlag,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.set_mail_item_archived(home, mail_item_id, archived)
            return result(home, "set_mail_item_archived")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "set_mail_item_archived",
            {"mail_item_id": mail_item_id, "archived": archived},
            invoke,
        )

    # Packages --------------------------------------------------------------

    @action_tool(
        description=gated_description(
            "Ask Casa to validate one tracking number. A POST, not a side-effect guarantee. "
            "Execution returns the validity flag and safe carrier IDs only.",
            "validate_package_tracking_number",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_validate_package_tracking_number(
        tracking_number: TrackingNumber,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(TrackingNumberValidationRequest, {"tracking_number": tracking_number})

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            response = await api.validate_package_tracking_number(home, tracking_number)
            carriers = [
                carrier
                for carrier in response.carrier_matches
                if SAFE_CARRIER_ID.fullmatch(carrier)
            ]
            return ActionResult(
                outcome="SUCCEEDED",
                operation="validate_package_tracking_number",
                home_id=home,
                tracking_number_valid=response.valid,
                carrier_ids=carriers[:MAX_CARRIER_IDS],
            )

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "validate_package_tracking_number",
            body.model_dump(mode="json"),
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Add a tracked package for one carrier with an explicit name and direction.",
            "add_tracked_package",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_add_tracked_package(
        carrier_id: PathId,
        tracking_number: TrackingNumber,
        name: Label,
        direction: PackageDirection,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            AddPackageRequest,
            {"tracking_number": tracking_number, "name": name, "direction": direction},
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.add_tracked_package(
                home, carrier_id, AddPackageRequest.model_validate_json(snapshot)
            )
            return result(home, "add_tracked_package")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "add_tracked_package",
            {"carrier_id": carrier_id, **body.model_dump(mode="json")},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Update one package's archive flag, name or direction. deleted=true may "
            "delete the package record and isn't a safe cancel. Supply at least one field.",
            "update_package",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_package(
        package_id: PathId,
        ctx: Context[AppContext],
        archive: StrictFlag | None = None,
        deleted: StrictFlag | None = None,
        name: Label | None = None,
        direction: PackageDirection | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        fields = {"archive": archive, "deleted": deleted, "name": name, "direction": direction}
        if all(value is None for value in fields.values()):
            raise failure("INVALID_ARGUMENT")
        body = build(UpdatePackageRequest, fields)
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_package(
                home, package_id, UpdatePackageRequest.model_validate_json(snapshot)
            )
            return result(home, "update_package")

        preview: dict[str, JsonValue] = {
            "package_id": package_id,
            **body.model_dump(mode="json", exclude_none=True),
        }
        if deleted is True:
            preview["risk"] = (
                "deleted=true may delete the package record. Not a safe cancel. No known undo."
            )
        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_package",
            preview,
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Requeue one package pickup. Eligibility and next window are chosen by Casa.",
            "requeue_package_pickup",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_requeue_package_pickup(
        package_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.requeue_package_pickup(home, package_id)
            return result(home, "requeue_package_pickup")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "requeue_package_pickup",
            {"package_id": package_id, "risk": "May schedule a new pickup."},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Set package auto-archive to 1-365 days or explicit null. The key is always sent. "
            "Range is local policy, not a known Casa limit.",
            "set_package_auto_archive",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_set_package_auto_archive(
        package_auto_archive_days: PackageArchiveDays | None,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            UpdatePackageAutoArchiveRequest,
            {"package_auto_archive_days": package_auto_archive_days},
        )

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            response = await api.set_package_auto_archive(home, package_auto_archive_days)
            if not response.success:
                raise unconfirmed()
            return result(home, "set_package_auto_archive")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "set_package_auto_archive",
            {
                **body.model_dump(mode="json"),
                "risk": "Archive and disposal effects are unknown.",
            },
            invoke,
        )

    # Inventory -------------------------------------------------------------

    @action_tool(
        description=gated_description(
            "Create one inventory entity in a room. No images, type, make or properties.",
            "create_inventory_entity",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_create_inventory_entity(
        room_id: EntityId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        app = ctx.request_context.lifespan_context
        # The SDK requires the body home to match the route home.
        selected = resolve_home(app, home_id)
        body = build(CreateEntityRequest, {"home_id": selected, "room_id": room_id})
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = CreateEntityRequest.model_validate_json(snapshot)
            if validated.home_id != home:
                raise failure("INTERNAL_ERROR")
            await api.create_inventory_entity(home, validated)
            return result(home, "create_inventory_entity")

        return prepare(
            app,
            selected,
            "create_inventory_entity",
            body.model_dump(mode="json", exclude_none=True),
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Create a light fixture and bulb in a room by entity type IDs and an open "
            "bulb kind string. No images.",
            "create_inventory_lighting",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_create_inventory_lighting(
        room_id: EntityId,
        fixture_entity_type_id: PathId,
        bulb_kind: PathId,
        ctx: Context[AppContext],
        bulb_entity_type_id: PathId | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            CreateLightingRequest,
            {
                "room_id": room_id,
                "fixture": {"entity_type_id": fixture_entity_type_id},
                "bulb": {"kind": bulb_kind, "entity_type_id": bulb_entity_type_id},
            },
        )
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.create_inventory_lighting(
                home, CreateLightingRequest.model_validate_json(snapshot)
            )
            return result(home, "create_inventory_lighting")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "create_inventory_lighting",
            body.model_dump(mode="json", exclude_none=True),
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Create a paint entity from a library color ID in one or more rooms.",
            "create_paint_from_library",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_create_paint_from_library(
        paint_color_id: CatalogNumber,
        room_ids: RoomIds,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            CreatePaintFromLibraryRequest,
            {"paint_color_id": paint_color_id, "room_ids": room_ids},
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.create_paint_from_library(
                home, CreatePaintFromLibraryRequest.model_validate_json(snapshot)
            )
            return result(home, "create_paint_from_library")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "create_paint_from_library",
            body.model_dump(mode="json"),
            invoke,
        )

    @action_tool(
        description=gated_description(
            "PATCH inventory properties. Each property supplies exactly one of value, "
            "enum_id or multi_enums. Merge semantics are unknown. No clear operation.",
            "update_entity_properties",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_entity_properties(
        entity_id: EntityId,
        props: PropertyUpdates,
        ctx: Context[AppContext],
        make_id: PathId | None = None,
        model_id: PathId | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        if not props and make_id is None and model_id is None:
            raise failure("INVALID_ARGUMENT")
        body = build(
            UpdateEntityPropertiesRequest,
            {
                "make_id": make_id,
                "model_id": model_id,
                "props": [prop.model_dump(exclude_none=True) for prop in props],
            },
        )
        snapshot = body.model_dump_json(exclude_none=True)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.update_entity_properties(
                home, entity_id, UpdateEntityPropertiesRequest.model_validate_json(snapshot)
            )
            return result(home, "update_entity_properties")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_entity_properties",
            {"entity_id": entity_id, **body.model_dump(mode="json", exclude_none=True)},
            invoke,
        )

    # AI and settings -------------------------------------------------------

    @action_tool(
        description=gated_description(
            "Remove the rating from one Casa AI message.", "clear_ai_message_rating"
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_clear_ai_message_rating(
        message_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            # The unknown response body is discarded, never forwarded.
            await api.clear_ai_message_rating(home, message_id)
            return result(home, "clear_ai_message_rating")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "clear_ai_message_rating",
            {"message_id": message_id},
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Replace all four home access and package pickup fields. Each is required and "
            "may be explicit null. Whether null clears a value is unknown.",
            "update_access_preferences",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_access_preferences(
        general_instructions: Content | None,
        package_pickup_method: PathId | None,
        package_pickup_spot: PathId | None,
        package_pickup_general_instructions: Content | None,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(
            UpdateAccessPreferencesRequest,
            {
                "general_instructions": general_instructions,
                "package_pickup_method": package_pickup_method,
                "package_pickup_spot": package_pickup_spot,
                "package_pickup_general_instructions": package_pickup_general_instructions,
            },
        )
        snapshot = body.model_dump_json()

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            validated = UpdateAccessPreferencesRequest.model_validate_json(snapshot)
            await api.update_access_preferences(
                home,
                general_instructions=validated.general_instructions,
                package_pickup_method=validated.package_pickup_method,
                package_pickup_spot=validated.package_pickup_spot,
                package_pickup_general_instructions=(validated.package_pickup_general_instructions),
            )
            return result(home, "update_access_preferences")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_access_preferences",
            {
                **body.model_dump(mode="json"),
                "risk": "Replaces instructions vendors use to access the home. "
                "null may clear a value.",
            },
            invoke,
        )
