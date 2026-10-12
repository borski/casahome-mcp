"""Separate, finite SDK action contract. Read-only fakes needn't implement it."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal, Protocol

from casahome.models.ai import CasaAIFeedbackResponse
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


class CasaActionsProtocol(Protocol):
    async def add_mailbox_recipient(
        self,
        home_id: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        business_name: str | None = None,
    ) -> MailboxRecipientResponse: ...
    async def update_mailbox_auto_archive(
        self,
        home_id: str,
        mailbox_auto_archive_days: int | None,
    ) -> MailboxAutoArchiveResponse: ...
    async def move_entity_to_room(
        self, home_id: str, entity_id: str, room_id: str
    ) -> BasicMessageResponse: ...
    async def rate_ai_message(
        self, home_id: str, message_id: str, rating: Literal["good", "bad"]
    ) -> CasaAIFeedbackResponse: ...
    async def respond_to_suggested_todo(
        self, home_id: str, suggestion_id: str, decision: str
    ) -> TodoDetailsResponse: ...
    async def send_todo_to_concierge(self, home_id: str, todo_id: str) -> TodoDetailsResponse: ...
    async def answer_todo_question(
        self,
        home_id: str,
        todo_id: str,
        round_id: str,
        question_id: str,
        *,
        answer: SingleSelectAnswer | MultiSelectAnswer | None = None,
        skip: bool = False,
    ) -> None: ...
    async def submit_todo_question_round(
        self,
        home_id: str,
        todo_id: str,
        round_id: str,
        answers: Sequence[SingleSelectRoundAnswer | MultiSelectRoundAnswer],
    ) -> TodoDetailsResponse: ...
    async def update_autopilot_plan(
        self,
        home_id: str,
        plan_id: str,
        *,
        enabled: bool,
        selected_cadence: str,
        next_desired_occurrence_date: date,
        associations_enabled_map: Mapping[str, bool] | None = None,
    ) -> BasicMessageResponse: ...
    async def update_notification_settings(
        self, home_id: str, settings: Sequence[NotificationSettingUpdate]
    ) -> NotificationSettingsResponse: ...
    async def send_ai_message(
        self,
        home_id: str,
        text: str,
        *,
        upload_ids: Sequence[str] = (),
        idempotency_key: str | None = None,
    ) -> SentCasaAIMessage: ...
    async def send_request_message(
        self, home_id: str, request_id: str, body: SendRequestMessageRequest
    ) -> SendRequestMessageResponse: ...
    async def create_todo_result(
        self, home_id: str, body: CreateTodoBody
    ) -> CreateTodoResponse: ...
    async def upload_document(
        self,
        home_id: str,
        source: bytes,
        filename: str,
        mimetype: str | None = None,
        *,
        find_todos: bool = True,
    ) -> CreateDocumentResponse: ...
    async def delete_todo(self, home_id: str, todo_id: str) -> None: ...
    async def update_entity_model(
        self, home_id: str, entity_id: str, model_name: str
    ) -> SaveAndPublishEntityResponse: ...
    async def update_entity_make_model(
        self,
        home_id: str,
        entity_id: str,
        *,
        make_id: str | None = None,
        make_name: str | None = None,
        model_id: str | None = None,
        model_name: str | None = None,
    ) -> SaveAndPublishEntityResponse: ...
    async def rename_room(
        self, home_id: str, room_id: str, *, room_type_id: str, name: str
    ) -> BasicMessageResponse: ...
    async def respond_to_document_structure_suggestion(
        self,
        home_id: str,
        document_id: str,
        suggestion_id: str,
        expected_values: Sequence[str],
        decision: Literal["accepted"] = "accepted",
    ) -> SavedResponse: ...
    async def update_access_preferences(
        self,
        home_id: str,
        *,
        general_instructions: str | None,
        package_pickup_method: str | None,
        package_pickup_spot: str | None,
        package_pickup_general_instructions: str | None,
    ) -> AccessPreferencesResponse: ...

    # Provisional SDK writes. Gated by the SDK marker at prepare and execute.
    async def update_todo(
        self, home_id: str, todo_id: str, body: UpdateTodoBody
    ) -> TodoDetailsResponse: ...
    async def reject_suggested_todo(
        self, home_id: str, todo_id: str, reason: TodoRejectionReason | None = None
    ) -> TodoDetailsResponse: ...
    async def confirm_todo_support(
        self, home_id: str, todo_id: str, is_support_question: bool
    ) -> TodoDetailsResponse: ...
    async def update_document(
        self, home_id: str, document_id: str, body: UpdateDocumentBody
    ) -> DocumentDetailsResponse: ...
    async def analyze_document(
        self, home_id: str, document_id: str, reanalyze: bool
    ) -> DocumentDetailsResponse: ...
    async def organize_document(
        self, home_id: str, document_id: str
    ) -> DocumentDetailsResponse: ...
    async def update_schedule_preferences(
        self, home_id: str, body: UpdateSchedulePreferencesRequest
    ) -> SchedulePreferencesResponse: ...
    async def update_availability_slots(
        self,
        home_id: str,
        availability_request_id: str,
        windows: Sequence[MemberAvailabilitySlotWindow],
    ) -> MemberAvailabilityDetail: ...
    async def reorder_todo_section(
        self,
        home_id: str,
        section: TodoOrderSection,
        *,
        expected_revision: int,
        ordered_item_ids: Sequence[str],
    ) -> ReorderTodoSectionResponse: ...
    async def retry_todo(self, home_id: str, todo_id: str) -> TodoDetailsResponse: ...
    async def cancel_vendor_visit(
        self, home_id: str, visit_id: str
    ) -> CancelVendorVisitResponse: ...
    async def remove_mailbox_recipient(
        self, home_id: str, recipient_id: str
    ) -> BasicMessageResponse: ...
    async def mark_mail_item_read(
        self, home_id: str, mail_item_id: str
    ) -> BasicMessageResponse: ...
    async def mark_mail_item_unread(
        self, home_id: str, mail_item_id: str
    ) -> BasicMessageResponse: ...
    async def set_mail_item_archived(
        self, home_id: str, mail_item_id: str, archived: bool
    ) -> BasicMessageResponse: ...
    async def validate_package_tracking_number(
        self, home_id: str, tracking_number: str
    ) -> TrackingNumberValidationResponse: ...
    async def add_tracked_package(
        self, home_id: str, carrier_id: str, body: AddPackageRequest
    ) -> BasicMessageResponse: ...
    async def update_package(
        self, home_id: str, package_id: str, body: UpdatePackageRequest
    ) -> BasicMessageResponse: ...
    async def requeue_package_pickup(
        self, home_id: str, package_id: str
    ) -> BasicMessageResponse: ...
    async def set_package_auto_archive(
        self, home_id: str, package_auto_archive_days: int | None
    ) -> UpdatePackageAutoArchiveResponse: ...
    async def create_inventory_entity(
        self, home_id: str, body: CreateEntityRequest
    ) -> CreateEntityResponse: ...
    async def create_inventory_lighting(
        self, home_id: str, body: CreateLightingRequest
    ) -> CreateLightingResponse: ...
    async def create_paint_from_library(
        self, home_id: str, body: CreatePaintFromLibraryRequest
    ) -> CreatePaintFromLibraryResponse: ...
    async def clear_ai_message_rating(self, home_id: str, message_id: str) -> JsonValue: ...
    async def update_entity_properties(
        self, home_id: str, entity_id: str, body: UpdateEntityPropertiesRequest
    ) -> BasicMessageResponse: ...
