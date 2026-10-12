"""Strict MCP inputs and small private action outputs."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

CONTENT_FIELDS = {
    "casa_prepare_send_ai_message": {"text"},
    "casa_prepare_send_request_message": {"content"},
    "casa_prepare_create_todo_result": {"content"},
    "casa_prepare_answer_todo_question": {"other_text"},
    "casa_prepare_submit_todo_question_round": {"other_text"},
    "casa_prepare_respond_to_document_structure_suggestion": {"expected_values"},
    "casa_prepare_update_todo": {"prepared_brief"},
    "casa_prepare_update_access_preferences": {
        "general_instructions",
        "package_pickup_general_instructions",
    },
}
CATALOG_SELECTION_FIELDS = {
    "casa_prepare_update_entity_make_model": frozenset(
        {"make_id", "make_name", "model_id", "model_name"}
    ),
}

PathId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$", strict=True)]
Content = Annotated[str, Field(min_length=1, max_length=10_000, strict=True)]
Token = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$", strict=True)]
StrictFlag = Annotated[bool, Field(strict=True)]
Index = Annotated[int, Field(ge=0, le=10_000, strict=True)]
RecipientName = Annotated[str, Field(min_length=1, max_length=256, strict=True)]
Label = Annotated[str, Field(min_length=1, max_length=1024, strict=True)]
CatalogName = Annotated[str, Field(min_length=1, max_length=256, strict=True)]
Emoji = Annotated[str, Field(min_length=1, max_length=16, strict=True)]
DocumentDate = Annotated[str, Field(min_length=1, max_length=64, strict=True)]
TrackingNumber = Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{1,64}$", strict=True)]
PackageDirection = Literal["inbound", "outbound", "unknown"]
Revision = Annotated[int, Field(ge=0, le=2**31 - 1, strict=True)]
CatalogNumber = Annotated[int, Field(ge=0, le=2**31 - 1, strict=True)]
PackageArchiveDays = Annotated[int, Field(ge=1, le=365, strict=True)]
DayOfWeek = Annotated[int, Field(ge=0, le=7, strict=True)]
SlotBound = Annotated[int, Field(ge=0, le=10**13, strict=True)]
DaysOfWeek = Annotated[list[DayOfWeek], Field(max_length=7)]
OptionalIds = Annotated[list[PathId], Field(max_length=100)]
OrderedIds = Annotated[list[PathId], Field(min_length=1, max_length=100)]


def validate_mailbox_archive_days(value: object) -> Literal[30] | None:
    # Literal's equality accepts 30.0. Require an actual JSON integer or null
    # before the SDK/MCP validators can coerce or echo rejected input values.
    if value is None:
        return None
    if type(value) is int and value == 30:
        return 30
    raise ValueError("Expected the observed integer or null.")


MailboxArchiveDays = Annotated[
    Literal[30] | None,
    BeforeValidator(validate_mailbox_archive_days),
]


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


class SlotWindow(InputModel):
    """Integer bounds as observed in the app codec. Units remain UNVERIFIED."""

    start_time: SlotBound
    end_time: SlotBound


SlotWindows = Annotated[list[SlotWindow], Field(max_length=100)]


class MultiEnumSelection(InputModel):
    id: PathId
    is_selected: StrictFlag


class PropertyUpdate(InputModel):
    """Exactly one value form per property. Combination semantics are UNVERIFIED."""

    definition_id: PathId
    value: Content | None = None
    enum_id: PathId | None = None
    multi_enums: Annotated[list[MultiEnumSelection], Field(min_length=1, max_length=100)] | None = (
        None
    )

    @model_validator(mode="after")
    def one_value_form(self) -> Self:
        forms = (self.value, self.enum_id, self.multi_enums)
        if sum(form is not None for form in forms) != 1:
            raise ValueError("Provide exactly one of value, enum_id or multi_enums.")
        return self


PropertyUpdates = Annotated[list[PropertyUpdate], Field(max_length=50)]


CATALOG_REJECTION_WARNING = (
    "Rejection doesn't prove complete rollback. Reconcile inventory before any new retry. "
    "Never automatically retry or prepare a replacement."
)


class ActionResult(InputModel):
    outcome: Literal[
        "SUCCEEDED", "UNKNOWN", "REJECTED_UNKNOWN_PRODUCT", "NOT_EXECUTED", "CANCELLED"
    ]
    operation: str
    home_id: str
    # Static safety guidance only, never upstream error text.
    warning: str | None = None
    # Status only. Never forward raw SDK response text, URLs or models.
    needs_support_confirmation: bool | None = None
    # Tracking-number validation status only. Carrier IDs are safe path segments.
    tracking_number_valid: bool | None = None
    carrier_ids: list[str] | None = None
