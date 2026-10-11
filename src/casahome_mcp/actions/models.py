"""Strict MCP inputs and small private action outputs."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTENT_FIELDS = {
    "casa_prepare_send_ai_message": {"text"},
    "casa_prepare_send_request_message": {"content"},
    "casa_prepare_create_todo_result": {"content"},
    "casa_prepare_answer_todo_question": {"other_text"},
    "casa_prepare_submit_todo_question_round": {"other_text"},
    "casa_prepare_respond_to_document_structure_suggestion": {"expected_values"},
}

PathId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$", strict=True)]
Content = Annotated[str, Field(min_length=1, max_length=10_000, strict=True)]
Token = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$", strict=True)]
StrictFlag = Annotated[bool, Field(strict=True)]
Index = Annotated[int, Field(ge=0, le=10_000, strict=True)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class SingleAnswer(InputModel):
    kind: Literal["single_select"]
    selected_option_index: Index
    other_text: Content | None = None


class MultiAnswer(InputModel):
    kind: Literal["multi_select"]
    selected_option_indexes: Annotated[list[Index], Field(min_length=1, max_length=100)]
    other_text: Content | None = None


Answer = Annotated[SingleAnswer | MultiAnswer, Field(discriminator="kind")]


class SingleRoundAnswer(InputModel):
    question_id: PathId
    input_kind: Literal["single_select"]
    selected_option_index: Index
    other_text: Content | None = None


class MultiRoundAnswer(InputModel):
    question_id: PathId
    input_kind: Literal["multi_select"]
    selected_option_indexes: Annotated[list[Index], Field(min_length=1, max_length=100)]
    other_text: Content | None = None


RoundAnswer = Annotated[SingleRoundAnswer | MultiRoundAnswer, Field(discriminator="input_kind")]
RoundAnswers = Annotated[list[RoundAnswer], Field(min_length=1, max_length=100)]


class NotificationUpdate(InputModel):
    notification_type: PathId
    channel: Literal["push"]
    enabled: StrictFlag


Notifications = Annotated[list[NotificationUpdate], Field(min_length=1, max_length=100)]
ExpectedValues = Annotated[
    list[Annotated[str, Field(max_length=10_000, strict=True)]], Field(max_length=100)
]


class ActionResult(InputModel):
    outcome: Literal["SUCCEEDED", "UNKNOWN", "NOT_EXECUTED", "CANCELLED"]
    operation: str
    home_id: str
    # Status only. Never forward raw SDK response text, URLs or models.
    needs_support_confirmation: bool | None = None
