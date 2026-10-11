"""Explicit typed action fake. No network, credentials or real uploads."""

import asyncio
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from casahome.models.ai import CasaAIFeedbackResponse, CasaAISendMessageResponse
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
from test_tools import SECRET, FakeCasa

from casahome_mcp.action_protocol import CasaActionsProtocol


class FakeActions(CasaActionsProtocol):
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
