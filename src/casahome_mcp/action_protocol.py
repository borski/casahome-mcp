"""Separate, finite SDK action contract. Read-only fakes needn't implement it."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal, Protocol

from casahome.models.ai import CasaAIFeedbackResponse
from casahome.models.documents import CreateDocumentResponse, SavedResponse
from casahome.models.entity_publish import SaveAndPublishEntityResponse
from casahome.models.preferences import NotificationSettingsResponse
from casahome.models.read_todos import TodoDetailsResponse
from casahome.models.todos import CreateTodoBody
from casahome.models.verified_writes import (
    MultiSelectAnswer,
    MultiSelectRoundAnswer,
    NotificationSettingUpdate,
    SingleSelectAnswer,
    SingleSelectRoundAnswer,
)
from casahome.models.write_contracts import (
    BasicMessageResponse,
    CreateTodoResponse,
    SendRequestMessageRequest,
    SendRequestMessageResponse,
)
from casahome.writes import SentCasaAIMessage


class CasaActionsProtocol(Protocol):
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
    async def respond_to_document_structure_suggestion(
        self,
        home_id: str,
        document_id: str,
        suggestion_id: str,
        expected_values: Sequence[str],
        decision: Literal["accepted"] = "accepted",
    ) -> SavedResponse: ...
