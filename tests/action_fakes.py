"""Explicit typed action fake. No network, credentials or real uploads."""

import asyncio
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from casahome.models.ai import CasaAIFeedbackResponse, CasaAISendMessageResponse
from casahome.models.availability import MemberAvailabilityDetail
from casahome.models.documents import (
    CreateDocumentResponse,
    DocumentDetailsResponse,
    SavedResponse,
)
from casahome.models.entity_publish import SaveAndPublishEntityResponse
from casahome.models.mail_workflows import (
    AddPackageRequest,
    CreateEntityRequest,
    CreateEntityResponse,
    CreateLightingRequest,
    CreateLightingResponse,
    CreatePaintFromLibraryRequest,
    CreatePaintFromLibraryResponse,
    MailboxAutoArchiveResponse,
    MailboxRecipientResponse,
    TrackingNumberValidationResponse,
    UpdatePackageAutoArchiveResponse,
    UpdatePackageRequest,
)
from casahome.models.preferences import (
    AccessPreferencesResponse,
    NotificationSettingsResponse,
    SchedulePreferencesResponse,
)
from casahome.models.read_todos import TodoDetailsResponse
from casahome.models.recovered_contracts import (
    HomeDocumentDeleteResponse,
    UpdateRequestDetailBody,
    UpdateRequestDetailResponse,
    UpdateStoryBody,
    UpdateTaskResponse,
    UpdateTaskScalarBody,
)
from casahome.models.todos import CreateTodoBody
from casahome.models.verified_writes import (
    MultiSelectAnswer,
    MultiSelectRoundAnswer,
    NotificationSettingUpdate,
    SingleSelectAnswer,
    SingleSelectRoundAnswer,
)
from casahome.models.workflows import (
    CancelVendorVisitResponse,
    MemberAvailabilitySlotWindow,
    ReorderTodoSectionResponse,
    TodoOrderSection,
    TodoRejectionReason,
    UpdateDocumentBody,
    UpdateSchedulePreferencesRequest,
    UpdateTodoBody,
)
from casahome.models.write_contracts import (
    BasicMessageResponse,
    CreateTodoResponse,
    SendRequestMessageRequest,
    SendRequestMessageResponse,
    UpdateEntityPropertiesRequest,
)
from casahome.writes import SentCasaAIMessage
from pydantic import JsonValue
from test_tools import SECRET, FakeCasa

from casahome_mcp.action_protocol import CasaActionsProtocol


class FakeActions(CasaActionsProtocol):
    async def update_request_detail(
        self, home_id: str, request_id: str, body: UpdateRequestDetailBody
    ) -> UpdateRequestDetailResponse:
        await self.record(
            "update_request_detail", home_id, request_id, body.model_dump(exclude_none=True)
        )
        return UpdateRequestDetailResponse.model_validate(
            {
                "id": request_id,
                "type": "general",
                "status": "open",
                "title": SECRET,
                "emoji": "x",
                "has_unread_messages": False,
            }
        )

    async def update_task(
        self, home_id: str, task_id: str, body: UpdateTaskScalarBody
    ) -> UpdateTaskResponse:
        await self.record("update_task", home_id, task_id, body.model_dump(exclude_none=True))
        return UpdateTaskResponse.model_validate(
            {
                "id": task_id,
                "title": SECRET,
                "description": SECRET,
                "emoji": "x",
                "status": "open",
                "updates": [],
                "can_schedule_handyman_vendor_visit": False,
                "can_chat_with_concierge": False,
                "can_edit": True,
                "can_delete": True,
            }
        )

    async def update_story(
        self, home_id: str, story_id: str, body: UpdateStoryBody
    ) -> BasicMessageResponse:
        await self.record("update_story", home_id, story_id, body.model_dump(exclude_none=True))
        return BasicMessageResponse(message=SECRET)

    async def dismiss_document_structure_suggestion(
        self, home_id: str, document_id: str, suggestion_id: str, expected_values: Sequence[str]
    ) -> SavedResponse:
        await self.record(
            "dismiss_document_structure_suggestion",
            home_id,
            document_id,
            suggestion_id,
            list(expected_values),
        )
        return SavedResponse(saved=True)

    async def delete_document(self, home_id: str, document_id: str) -> HomeDocumentDeleteResponse:
        await self.record("delete_document", home_id, document_id)
        return HomeDocumentDeleteResponse(deleted=True)

    def __init__(self, reads: FakeCasa) -> None:
        self.reads = reads
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.error: Exception | None = None
        self.release: asyncio.Event | None = None
        self.entered = asyncio.Event()

    async def record(self, name: str, *args: object) -> None:
        self.calls.append((name, args))
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.error is not None:
            raise self.error

    async def add_mailbox_recipient(
        self,
        home_id: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        business_name: str | None = None,
    ) -> MailboxRecipientResponse:
        await self.record("add_mailbox_recipient", home_id, first_name, last_name, business_name)
        return MailboxRecipientResponse.model_validate(
            {
                "recipient": {
                    "id": "recipient-one",
                    "kind": SECRET,
                    "first_name": SECRET,
                    "last_name": SECRET,
                    "address": {"line1": SECRET},
                    "url": "https://example.invalid/" + SECRET,
                }
            }
        )

    async def update_mailbox_auto_archive(
        self,
        home_id: str,
        mailbox_auto_archive_days: int | None,
    ) -> MailboxAutoArchiveResponse:
        await self.record("update_mailbox_auto_archive", home_id, mailbox_auto_archive_days)
        return MailboxAutoArchiveResponse.model_validate(
            {
                "success": True,
                "mailbox_auto_archive_days": mailbox_auto_archive_days,
                "message": SECRET,
            }
        )

    async def move_entity_to_room(
        self,
        home_id: str,
        entity_id: str,
        room_id: str,
    ) -> BasicMessageResponse:
        await self.record("move_entity_to_room", home_id, entity_id, room_id)
        return BasicMessageResponse(message=SECRET)

    async def rate_ai_message(
        self,
        home_id: str,
        message_id: str,
        rating: Literal["good", "bad"],
    ) -> CasaAIFeedbackResponse:
        await self.record("rate_ai_message", home_id, message_id, rating)
        return CasaAIFeedbackResponse.model_validate(
            {"success": True, "feedback": {"rating": rating}}
        )

    async def respond_to_suggested_todo(
        self,
        home_id: str,
        suggestion_id: str,
        decision: str,
    ) -> TodoDetailsResponse:
        await self.record("respond_to_suggested_todo", home_id, suggestion_id, decision)
        return self.reads.todo_result

    async def send_todo_to_concierge(self, home_id: str, todo_id: str) -> TodoDetailsResponse:
        await self.record("send_todo_to_concierge", home_id, todo_id)
        return self.reads.todo_result

    async def answer_todo_question(
        self,
        home_id: str,
        todo_id: str,
        round_id: str,
        question_id: str,
        *,
        answer: SingleSelectAnswer | MultiSelectAnswer | None = None,
        skip: bool = False,
    ) -> None:
        await self.record(
            "answer_todo_question",
            home_id,
            todo_id,
            round_id,
            question_id,
            answer.model_dump() if answer else None,
            skip,
        )

    async def submit_todo_question_round(
        self,
        home_id: str,
        todo_id: str,
        round_id: str,
        answers: Sequence[SingleSelectRoundAnswer | MultiSelectRoundAnswer],
    ) -> TodoDetailsResponse:
        await self.record(
            "submit_todo_question_round",
            home_id,
            todo_id,
            round_id,
            [answer.model_dump() for answer in answers],
        )
        return self.reads.todo_result

    async def update_autopilot_plan(
        self,
        home_id: str,
        plan_id: str,
        *,
        enabled: bool,
        selected_cadence: str,
        next_desired_occurrence_date: date,
        associations_enabled_map: Mapping[str, bool] | None = None,
    ) -> BasicMessageResponse:
        await self.record(
            "update_autopilot_plan",
            home_id,
            plan_id,
            enabled,
            selected_cadence,
            next_desired_occurrence_date,
            associations_enabled_map,
        )
        return BasicMessageResponse(message=SECRET)

    async def update_notification_settings(
        self,
        home_id: str,
        settings: Sequence[NotificationSettingUpdate],
    ) -> NotificationSettingsResponse:
        await self.record(
            "update_notification_settings", home_id, [setting.model_dump() for setting in settings]
        )
        return self.reads.notifications

    async def send_ai_message(
        self,
        home_id: str,
        text: str,
        *,
        upload_ids: Sequence[str] = (),
        idempotency_key: str | None = None,
    ) -> SentCasaAIMessage:
        await self.record("send_ai_message", home_id, text, tuple(upload_ids), idempotency_key)
        return SentCasaAIMessage(
            SECRET,
            CasaAISendMessageResponse.model_validate(
                {"member_message": {"id": "message-one", "content": SECRET}}
            ),
        )

    async def send_request_message(
        self,
        home_id: str,
        request_id: str,
        body: SendRequestMessageRequest,
    ) -> SendRequestMessageResponse:
        await self.record(
            "send_request_message", home_id, request_id, body.model_dump(exclude_none=True)
        )
        return SendRequestMessageResponse.model_validate(
            {
                "message": {
                    "id": "message-one",
                    "created_at": 1,
                    "sender_role": "member",
                    "sender_name": SECRET,
                }
            }
        )

    async def create_todo_result(self, home_id: str, body: CreateTodoBody) -> CreateTodoResponse:
        await self.record("create_todo_result", home_id, body.model_dump(exclude_none=True))
        return CreateTodoResponse(todo=self.reads.todo_result.todo, needs_support_confirmation=True)

    async def upload_document(
        self,
        home_id: str,
        source: bytes,
        filename: str,
        mimetype: str | None = None,
        *,
        find_todos: bool = True,
    ) -> CreateDocumentResponse:
        await self.record("upload_document", home_id, source, filename, mimetype, find_todos)
        return CreateDocumentResponse.model_validate(
            {"document": {"id": "document-one", "url": SECRET}, "already_exists": False}
        )

    async def delete_todo(self, home_id: str, todo_id: str) -> None:
        await self.record("delete_todo", home_id, todo_id)

    async def update_entity_model(
        self,
        home_id: str,
        entity_id: str,
        model_name: str,
    ) -> SaveAndPublishEntityResponse:
        await self.record("update_entity_model", home_id, entity_id, model_name)
        return SaveAndPublishEntityResponse.model_validate(
            {
                "entity_id": entity_id,
                "status": "published",
                "make": {"id": "make-one", "name": SECRET},
                "model": {"id": "model-one", "name": SECRET},
                "identity": {"state": "verified"},
            }
        )

    async def update_entity_make_model(
        self,
        home_id: str,
        entity_id: str,
        *,
        make_id: str | None = None,
        make_name: str | None = None,
        model_id: str | None = None,
        model_name: str | None = None,
    ) -> SaveAndPublishEntityResponse:
        await self.record(
            "update_entity_make_model", home_id, entity_id, make_id, make_name, model_id, model_name
        )
        return SaveAndPublishEntityResponse.model_validate(
            {
                "entity_id": entity_id,
                "status": "published",
                "make": {"id": "make-one", "name": SECRET},
                "model": {"id": "model-one", "name": SECRET},
                "identity": {"state": "verified", "candidates": [{"password": SECRET}]},
                "url": "https://example.invalid/" + SECRET,
            }
        )

    async def rename_room(
        self, home_id: str, room_id: str, *, room_type_id: str, name: str
    ) -> BasicMessageResponse:
        await self.record("rename_room", home_id, room_id, room_type_id, name)
        return BasicMessageResponse(message=SECRET)

    async def respond_to_document_structure_suggestion(
        self,
        home_id: str,
        document_id: str,
        suggestion_id: str,
        expected_values: Sequence[str],
        decision: Literal["accepted"] = "accepted",
    ) -> SavedResponse:
        await self.record(
            "respond_to_document_structure_suggestion",
            home_id,
            document_id,
            suggestion_id,
            list(expected_values),
            decision,
        )
        return SavedResponse(saved=True)

    async def update_access_preferences(
        self,
        home_id: str,
        *,
        general_instructions: str | None,
        package_pickup_method: str | None,
        package_pickup_spot: str | None,
        package_pickup_general_instructions: str | None,
    ) -> AccessPreferencesResponse:
        await self.record(
            "update_access_preferences",
            home_id,
            general_instructions,
            package_pickup_method,
            package_pickup_spot,
            package_pickup_general_instructions,
        )
        return AccessPreferencesResponse(home_id=home_id, general_instructions=SECRET)

    # Provisional workflow writes. Bodies are recorded in their wire JSON form.

    async def update_todo(
        self, home_id: str, todo_id: str, body: UpdateTodoBody
    ) -> TodoDetailsResponse:
        await self.record(
            "update_todo", home_id, todo_id, body.model_dump(mode="json", exclude_none=True)
        )
        return self.reads.todo_result

    async def reject_suggested_todo(
        self, home_id: str, todo_id: str, reason: TodoRejectionReason | None = None
    ) -> TodoDetailsResponse:
        await self.record("reject_suggested_todo", home_id, todo_id, reason)
        return self.reads.todo_result

    async def confirm_todo_support(
        self, home_id: str, todo_id: str, is_support_question: bool
    ) -> TodoDetailsResponse:
        await self.record("confirm_todo_support", home_id, todo_id, is_support_question)
        return self.reads.todo_result

    async def update_document(
        self, home_id: str, document_id: str, body: UpdateDocumentBody
    ) -> DocumentDetailsResponse:
        await self.record(
            "update_document",
            home_id,
            document_id,
            body.model_dump(mode="json", exclude_unset=True),
        )
        return self.reads.document

    async def analyze_document(
        self, home_id: str, document_id: str, reanalyze: bool
    ) -> DocumentDetailsResponse:
        await self.record("analyze_document", home_id, document_id, reanalyze)
        return self.reads.document

    async def organize_document(self, home_id: str, document_id: str) -> DocumentDetailsResponse:
        await self.record("organize_document", home_id, document_id)
        return self.reads.document

    async def update_schedule_preferences(
        self, home_id: str, body: UpdateSchedulePreferencesRequest
    ) -> SchedulePreferencesResponse:
        await self.record("update_schedule_preferences", home_id, body.model_dump(mode="json"))
        return self.reads.schedule

    async def update_availability_slots(
        self,
        home_id: str,
        availability_request_id: str,
        windows: Sequence[MemberAvailabilitySlotWindow],
    ) -> MemberAvailabilityDetail:
        await self.record(
            "update_availability_slots",
            home_id,
            availability_request_id,
            [window.model_dump(mode="json") for window in windows],
        )
        return self.reads.availability

    async def reorder_todo_section(
        self,
        home_id: str,
        section: TodoOrderSection,
        *,
        expected_revision: int,
        ordered_item_ids: Sequence[str],
    ) -> ReorderTodoSectionResponse:
        await self.record(
            "reorder_todo_section", home_id, section, expected_revision, list(ordered_item_ids)
        )
        return ReorderTodoSectionResponse.model_validate(
            {"section": {"name": section, "title": SECRET}}
        )

    async def retry_todo(self, home_id: str, todo_id: str) -> TodoDetailsResponse:
        await self.record("retry_todo", home_id, todo_id)
        return self.reads.todo_result

    async def cancel_vendor_visit(self, home_id: str, visit_id: str) -> CancelVendorVisitResponse:
        await self.record("cancel_vendor_visit", home_id, visit_id)
        return CancelVendorVisitResponse(id=visit_id, status=SECRET)

    async def remove_mailbox_recipient(
        self, home_id: str, recipient_id: str
    ) -> BasicMessageResponse:
        await self.record("remove_mailbox_recipient", home_id, recipient_id)
        return BasicMessageResponse(message=SECRET)

    async def mark_mail_item_read(self, home_id: str, mail_item_id: str) -> BasicMessageResponse:
        await self.record("mark_mail_item_read", home_id, mail_item_id)
        return BasicMessageResponse(message=SECRET)

    async def mark_mail_item_unread(self, home_id: str, mail_item_id: str) -> BasicMessageResponse:
        await self.record("mark_mail_item_unread", home_id, mail_item_id)
        return BasicMessageResponse(message=SECRET)

    async def set_mail_item_archived(
        self, home_id: str, mail_item_id: str, archived: bool
    ) -> BasicMessageResponse:
        await self.record("set_mail_item_archived", home_id, mail_item_id, archived)
        return BasicMessageResponse(message=SECRET)

    async def validate_package_tracking_number(
        self, home_id: str, tracking_number: str
    ) -> TrackingNumberValidationResponse:
        await self.record("validate_package_tracking_number", home_id, tracking_number)
        return TrackingNumberValidationResponse(
            tracking_number=SECRET, valid=True, carrier_matches=["carrier-one", SECRET + "/x"]
        )

    async def add_tracked_package(
        self, home_id: str, carrier_id: str, body: AddPackageRequest
    ) -> BasicMessageResponse:
        await self.record("add_tracked_package", home_id, carrier_id, body.model_dump(mode="json"))
        return BasicMessageResponse(message=SECRET)

    async def update_package(
        self, home_id: str, package_id: str, body: UpdatePackageRequest
    ) -> BasicMessageResponse:
        await self.record(
            "update_package", home_id, package_id, body.model_dump(mode="json", exclude_none=True)
        )
        return BasicMessageResponse(message=SECRET)

    async def requeue_package_pickup(self, home_id: str, package_id: str) -> BasicMessageResponse:
        await self.record("requeue_package_pickup", home_id, package_id)
        return BasicMessageResponse(message=SECRET)

    async def set_package_auto_archive(
        self, home_id: str, package_auto_archive_days: int | None
    ) -> UpdatePackageAutoArchiveResponse:
        await self.record("set_package_auto_archive", home_id, package_auto_archive_days)
        return UpdatePackageAutoArchiveResponse(
            success=True, package_auto_archive_days=package_auto_archive_days
        )

    async def create_inventory_entity(
        self, home_id: str, body: CreateEntityRequest
    ) -> CreateEntityResponse:
        await self.record(
            "create_inventory_entity", home_id, body.model_dump(mode="json", exclude_none=True)
        )
        return CreateEntityResponse(entity_id="entity-new", message=SECRET)

    async def create_inventory_lighting(
        self, home_id: str, body: CreateLightingRequest
    ) -> CreateLightingResponse:
        await self.record(
            "create_inventory_lighting", home_id, body.model_dump(mode="json", exclude_none=True)
        )
        return CreateLightingResponse(fixture_entity_id="fixture-new", message=SECRET)

    async def create_paint_from_library(
        self, home_id: str, body: CreatePaintFromLibraryRequest
    ) -> CreatePaintFromLibraryResponse:
        await self.record("create_paint_from_library", home_id, body.model_dump(mode="json"))
        return CreatePaintFromLibraryResponse(entity_id="paint-new")

    async def clear_ai_message_rating(self, home_id: str, message_id: str) -> JsonValue:
        await self.record("clear_ai_message_rating", home_id, message_id)
        return {"secret": SECRET}

    async def update_entity_properties(
        self, home_id: str, entity_id: str, body: UpdateEntityPropertiesRequest
    ) -> BasicMessageResponse:
        await self.record(
            "update_entity_properties",
            home_id,
            entity_id,
            body.model_dump(mode="json", exclude_none=True),
        )
        return BasicMessageResponse(message=SECRET)
