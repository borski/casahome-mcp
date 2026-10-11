"""Strict, allowlisted MCP output models, independent of the SDK wire models."""

from datetime import UTC, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

Source = Literal["configuration", "runtime", "casa"]
Confidence = Literal["LOCAL", "UNVERIFIED", "VERIFIED"]
InventoryKind = Literal["entities", "rooms"]
RequestLane = Literal["requests", "todos"]


class OutputModel(BaseModel):
    """Reject coercion and unexpected fields at every projected nesting level."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


T = TypeVar("T", bound=OutputModel)


class ToolResponse(OutputModel, Generic[T]):
    source: Source
    confidence: Confidence
    home_id: str | None
    fetched_at: datetime | None
    warnings: list[str]
    data: T

    @field_validator("fetched_at")
    @classmethod
    def normalize_retrieval_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("Retrieval time must be timezone-aware.")
        return value.astimezone(UTC)


class Page(OutputModel, Generic[T]):
    """A local slice, not a claim about upstream pagination or service totals."""

    items: list[T]
    offset: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    total_in_response: int = Field(ge=0)
    has_more_in_response: bool
    next_offset: int | None = Field(ge=0)
    pagination_scope: Literal["single_upstream_response"] = "single_upstream_response"


class StatusData(OutputModel):
    version: str
    token_configured: bool
    configured_home_count: int
    allow_unverified_reads: bool
    refresh_token_rotated: bool
    disabled_features: list[str]


class HomeSummary(OutputModel):
    id: str
    label: str


class HomesData(OutputModel):
    homes: list[HomeSummary]


class BadgeData(OutputModel):
    computed_at: int
    total: int
    features: dict[str, int]


class WeatherData(OutputModel):
    temperature_degrees: float = Field(allow_inf_nan=False)
    temperature_units: str
    condition_type: str
    sunrise_at: int | None
    sunset_at: int | None


class RoomSummary(OutputModel):
    id: str
    name: str
    story_id: str
    story_name: str
    floor_number: int


class EntitySummary(OutputModel):
    id: str
    category_id: str
    category: str
    status: str
    type_id: str | None
    type: str | None
    rooms: list[str]
    stories: list[str]


class InventoryData(OutputModel):
    kind: InventoryKind
    page: Page[EntitySummary | RoomSummary]


class RequestCardSummary(OutputModel):
    id: str
    type: str
    title: str
    updated_at: int
    has_unread_messages: bool
    pending_invoice_count: int
    pending_purchase_count: int
    pending_schedule_prompt_count: int
    concierge_awaiting_reply: bool
    section_name: str
    section_title: str | None


class TodoSummary(OutputModel):
    kind: str
    id: str
    title: str
    updated_at: int
    state: str
    origin_todo_id: str | None
    section_name: str
    section_title: str | None


class RequestsData(OutputModel):
    lane: RequestLane
    completed_count: int | None
    page: Page[RequestCardSummary | TodoSummary]


class MessageSummary(OutputModel):
    id: str
    created_at: int
    sender_role: str
    sender_name: str
    content: str | None


class RequestData(OutputModel):
    id: str
    type: str
    status: str
    title: str
    created_at: int
    updated_at: int
    has_unread_messages: bool
    messages: Page[MessageSummary] | None


class CalendarEventSummary(OutputModel):
    id: str
    start_time: int
    end_time: int


class CalendarData(OutputModel):
    page: Page[CalendarEventSummary]


class CreditsData(OutputModel):
    home_id: str
    total_available: int
    handyman_hourly_rate_cents: int


class MailboxSummary(OutputModel):
    id: str
    status: str
    onboarding_status: str
    claimed_at: str
    auto_archive_days: int | None


class MailboxData(OutputModel):
    mailbox: MailboxSummary | None


class MailItemSummary(OutputModel):
    id: str
    scan_status: str
    received_at: str
    archived_at: str | None
    read_at: str | None
    forward_status: str | None
    shred_status: str | None
    deposit_status: str | None
    summary: str | None


class MailItemsData(OutputModel):
    page: Page[MailItemSummary]


class PackageSummary(OutputModel):
    id: str
    name: str | None
    carrier_id: str
    created_at: int
    updated_at: int
    status: str
    status_detail: str
    direction: str
    archived: bool
    is_pickup: bool
    est_delivery_date: int | None
    pickup_status: str | None


class PackagesData(OutputModel):
    page: Page[PackageSummary]
