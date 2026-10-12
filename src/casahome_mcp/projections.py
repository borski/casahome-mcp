"""Pure projections from permissive Casa models to explicit, bounded DTOs.

Only selected page items are projected. Warnings describe the returned data.
The tool layer owns envelope size checks and sanitized SDK/validation errors.
"""

import re
from collections.abc import Callable, Sequence
from typing import Literal, TypeVar

from casahome.models.bootstrap import HomeBadgeCounts
from casahome.models.calendar import CalendarEvent, VisitsCalendarResponse
from casahome.models.credits import MemberCredits
from casahome.models.home import (
    HomeDetailsResponse,
    HomeRoom,
    HomeStory,
    PropertyValue,
    SimpleEntity,
    WeatherResponse,
)
from casahome.models.mailbox import (
    MailboxMailItem,
    MailboxMailItemsResponse,
    MailboxOverviewResponse,
    PackageItem,
    PackagesResponse,
)
from casahome.models.requests import RequestCard, RequestDetails, RequestMessage, RequestsResponse
from casahome.models.todos import TodoLaneCard

from casahome_mcp.outputs import (
    BadgeData,
    CalendarData,
    CalendarEventSummary,
    CreditsData,
    EntityPropertySummary,
    EntitySummary,
    InventoryData,
    InventoryItemData,
    InventoryKind,
    MailboxData,
    MailboxSummary,
    MailItemsData,
    MailItemSummary,
    MessageSummary,
    OutputModel,
    PackagesData,
    PackageSummary,
    Page,
    RequestCardSummary,
    RequestData,
    RequestLane,
    RequestsData,
    RoomSummary,
    TodoSummary,
    WeatherData,
)

S = TypeVar("S")
T = TypeVar("T", bound=OutputModel)
ProjectionCode = Literal["INVALID_ARGUMENT", "NOT_FOUND", "OUTPUT_TOO_LARGE"]
MAX_ENTITY_PROPERTIES = 20
# Media links and their cache keys never leave the adapter, even inside properties.
_URL_KEY = re.compile(
    r"url|cache|thumbnail"
    r"|(?:^|[^a-z0-9])(?:uri|media|images?|photos?|manuals?|attachments?|videos?)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_URL_VALUE = re.compile(
    r"(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://"
    r"|(?<![a-z0-9])(?://|www\.|data:|mailto:|tel:|javascript:)"
    r"|(?:^|\s)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b",
    re.IGNORECASE,
)
_ROOM_TYPE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


class ProjectionError(Exception):
    """A fixed code only, never upstream values or validation exception text."""

    def __init__(self, code: ProjectionCode) -> None:
        self.code = code
        super().__init__(code)


def validate_pagination(*, offset: int, limit: int) -> None:
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
        raise ProjectionError("INVALID_ARGUMENT")


def page(
    items: Sequence[S],
    *,
    project: Callable[[S], T],
    offset: int = 0,
    limit: int = 25,
) -> Page[T]:
    """Slice one upstream collection before projection, with unbounded offsets."""

    validate_pagination(offset=offset, limit=limit)
    selected = [project(item) for item in items[offset : offset + limit]]
    next_offset = offset + len(selected)
    has_more = next_offset < len(items)
    return Page[T](
        items=selected,
        offset=offset,
        returned_count=len(selected),
        total_in_response=len(items),
        has_more_in_response=has_more,
        next_offset=next_offset if has_more else None,
    )


def _warn(warnings: list[str], code: str) -> None:
    if code not in warnings:
        warnings.append(code)


def _clip(text: str, maximum: int, warnings: list[str]) -> str:
    if len(text) <= maximum:
        return text
    _warn(warnings, "TEXT_TRUNCATED")
    return text[:maximum]


def _optional_clip(text: str | None, maximum: int, warnings: list[str]) -> str | None:
    return None if text is None else _clip(text, maximum, warnings)


def _ids(items: list[str], warnings: list[str]) -> list[str]:
    if len(items) > 100:
        _warn(warnings, "NESTED_COLLECTION_TRUNCATED")
    return items[:100]


def project_badges(model: HomeBadgeCounts) -> tuple[BadgeData, list[str]]:
    if len(model.features) > 100 or any(len(key) > 128 for key in model.features):
        raise ProjectionError("OUTPUT_TOO_LARGE")
    return BadgeData(
        computed_at=model.computed_at,
        total=model.total,
        features=dict(model.features),
    ), []


def project_weather(model: WeatherResponse) -> tuple[WeatherData, list[str]]:
    return WeatherData(
        temperature_degrees=model.temperature_degrees,
        temperature_units=model.temperature_units,
        condition_type=str(model.condition_type),
        sunrise_at=model.sunrise_at,
        sunset_at=model.sunset_at,
    ), []


def _scalar_text(value: PropertyValue) -> str | None:
    """Render a property scalar as text. JSON spelling for booleans."""
    match value:
        case None:
            return None
        case bool():
            return "true" if value else "false"
        case _:
            return str(value)


def _safe_entity_text(text: str | None, maximum: int, warnings: list[str]) -> str | None:
    if text is not None and _URL_VALUE.search(text):
        _warn(warnings, "URL_PROPERTY_OMITTED")
        return None
    return _optional_clip(text, maximum, warnings)


def _is_media_field(text: str) -> bool:
    # Split camelCase before matching whole media words. Don't drop "security"
    # or "immediate" just because they contain "uri" or "media".
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    return _URL_KEY.search(normalized) is not None


def _entity_properties(model: SimpleEntity, warnings: list[str]) -> list[EntityPropertySummary]:
    """Non-null, non-URL entity properties in source order, at most 20."""
    selected: list[EntityPropertySummary] = []
    for prop in model.entity_properties:
        text = _scalar_text(prop.value)
        if text is None:
            continue
        if (
            _is_media_field(prop.key)
            or _is_media_field(prop.title)
            or _URL_VALUE.search(prop.key)
            or _URL_VALUE.search(prop.title)
            or _URL_VALUE.search(text)
        ):
            _warn(warnings, "URL_PROPERTY_OMITTED")
            continue
        if len(selected) == MAX_ENTITY_PROPERTIES:
            _warn(warnings, "NESTED_COLLECTION_TRUNCATED")
            break
        selected.append(
            EntityPropertySummary(
                key=_clip(prop.key, 256, warnings),
                title=_clip(prop.title, 256, warnings),
                value=_clip(text, 256, warnings),
            )
        )
    return selected


def _entity(
    model: SimpleEntity, warnings: list[str], *, include_model_summary: bool = False
) -> EntitySummary:
    catalog_model = model.model
    model_summary = (
        _scalar_text(catalog_model.property_value("summary"))
        if include_model_summary and catalog_model is not None
        else None
    )
    return EntitySummary(
        id=model.id,
        category_id=model.category_id,
        category=_clip(model.category, 256, warnings),
        status=model.status,
        type_id=model.type_id,
        type=_optional_clip(model.type, 256, warnings),
        rooms=_ids(model.rooms, warnings),
        stories=_ids(model.stories, warnings),
        make=_safe_entity_text(None if model.make is None else model.make.name, 256, warnings),
        model=_safe_entity_text(
            None if catalog_model is None else catalog_model.name, 256, warnings
        ),
        serial_number=_safe_entity_text(
            _scalar_text(model.property_value("serial_number")), 256, warnings
        ),
        identity_state=_safe_entity_text(
            None if model.identity is None else model.identity.state, 256, warnings
        ),
        properties=_entity_properties(model, warnings),
        model_summary=_safe_entity_text(model_summary, 2000, warnings),
    )


def _room(model: HomeRoom, story: HomeStory, warnings: list[str]) -> RoomSummary:
    return RoomSummary(
        id=model.id,
        name=_clip(model.name, 256, warnings),
        story_id=story.id,
        story_name=_clip(story.name, 256, warnings),
        floor_number=story.floor_number,
        room_type_id=_room_type_id(model.room_type_id, warnings),
    )


def _room_type_id(value: str | None, warnings: list[str]) -> str | None:
    """Pass through only a safe room-type selector, never odd upstream text."""
    if value is None:
        return None
    if _ROOM_TYPE_ID.fullmatch(value):
        return value
    _warn(warnings, "ROOM_TYPE_ID_OMITTED")
    return None


def project_inventory(
    model: HomeDetailsResponse,
    *,
    kind: InventoryKind = "entities",
    offset: int = 0,
    limit: int = 25,
    room: str | None = None,
    category: str | None = None,
    include_model_summary: bool = False,
) -> tuple[InventoryData, list[str]]:
    """Page rooms or entities. ``room``/``category`` are exact entity filters."""
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    result: Page[EntitySummary | RoomSummary]
    if kind == "entities":
        room_ids = {
            label
            for story in model.home.stories
            for item in story.rooms
            if room in (item.id, item.name)
            for label in (item.id, item.name)
        }
        if room is not None:
            room_ids.add(room)
        entities = [
            entity
            for entity in model.entities
            if (room is None or not room_ids.isdisjoint(entity.rooms))
            and (category is None or entity.category == category)
        ]
        result = page(
            entities,
            project=lambda item: _entity(
                item, warnings, include_model_summary=include_model_summary
            ),
            offset=offset,
            limit=limit,
        )
    elif kind == "rooms":
        if room is not None or category is not None or include_model_summary:
            raise ProjectionError("INVALID_ARGUMENT")
        rooms = [(item, story) for story in model.home.stories for item in story.rooms]
        result = page(
            rooms,
            project=lambda item: _room(item[0], item[1], warnings),
            offset=offset,
            limit=limit,
        )
    else:
        raise ProjectionError("INVALID_ARGUMENT")
    return InventoryData(kind=kind, page=result), warnings


def project_inventory_item(
    model: HomeDetailsResponse, *, entity_id: str, include_model_summary: bool = False
) -> tuple[InventoryItemData, list[str]]:
    """Project the first entity whose ID matches ``entity_id`` case-insensitively."""
    wanted = entity_id.lower()
    entity = next((item for item in model.entities if item.id.lower() == wanted), None)
    if entity is None:
        raise ProjectionError("NOT_FOUND")
    warnings: list[str] = []
    return InventoryItemData(
        entity=_entity(entity, warnings, include_model_summary=include_model_summary)
    ), warnings


def _request_card(
    model: RequestCard, section_name: str, section_title: str | None, warnings: list[str]
) -> RequestCardSummary:
    return RequestCardSummary(
        id=model.id,
        type=str(model.type),
        title=_clip(model.title, 256, warnings),
        updated_at=model.updated_at,
        has_unread_messages=model.has_unread_messages,
        pending_invoice_count=model.pending_invoice_count,
        pending_purchase_count=model.pending_purchase_count,
        pending_schedule_prompt_count=model.pending_schedule_prompt_count,
        concierge_awaiting_reply=model.concierge_awaiting_reply,
        section_name=section_name,
        section_title=_optional_clip(section_title, 256, warnings),
    )


def _todo(
    model: TodoLaneCard, section_name: str, section_title: str, warnings: list[str]
) -> TodoSummary:
    return TodoSummary(
        kind=str(model.kind),
        id=model.id,
        title=_clip(model.title, 256, warnings),
        updated_at=model.updated_at,
        state=str(model.state),
        origin_todo_id=model.origin_todo_id,
        section_name=section_name,
        section_title=_clip(section_title, 256, warnings),
    )


def project_requests(
    model: RequestsResponse,
    *,
    lane: RequestLane = "requests",
    offset: int = 0,
    limit: int = 25,
) -> tuple[RequestsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    result: Page[RequestCardSummary | TodoSummary]
    completed_count: int | None = None
    if lane == "requests":
        cards: list[tuple[RequestCard, str, str | None]] = [
            (card, "needs_review", None) for card in model.requests.needs_review
        ]
        cards.extend(
            (card, section.name, section.title)
            for section in model.requests.sections
            for card in section.items
        )
        completed_count = model.requests.completed_count
        result = page(
            cards,
            project=lambda item: _request_card(item[0], item[1], item[2], warnings),
            offset=offset,
            limit=limit,
        )
    elif lane == "todos":
        if model.todos is None:
            _warn(warnings, "TODOS_LANE_ABSENT")
        todos = [
            (card, section.name, section.title)
            for section in (model.todos.sections if model.todos is not None else [])
            for card in section.items
        ]
        result = page(
            todos,
            project=lambda item: _todo(item[0], item[1], item[2], warnings),
            offset=offset,
            limit=limit,
        )
    else:
        raise ProjectionError("INVALID_ARGUMENT")
    return RequestsData(lane=lane, completed_count=completed_count, page=result), warnings


def _message(model: RequestMessage, warnings: list[str]) -> MessageSummary:
    return MessageSummary(
        id=model.id,
        created_at=model.created_at,
        sender_role=str(model.sender_role),
        sender_name=_clip(model.sender_name, 256, warnings),
        content=_optional_clip(model.content, 2000, warnings),
    )


def project_request(
    model: RequestDetails,
    *,
    include_messages: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[RequestData, list[str]]:
    validate_pagination(offset=offset, limit=limit)
    warnings: list[str] = []
    messages: Page[MessageSummary] | None = None
    if include_messages:
        _warn(warnings, "UPSTREAM_COMPLETENESS_UNKNOWN")
        messages = page(
            model.messages,
            project=lambda item: _message(item, warnings),
            offset=offset,
            limit=limit,
        )
    return RequestData(
        id=model.id,
        type=str(model.type),
        status=str(model.status),
        title=_clip(model.title, 256, warnings),
        created_at=model.created_at,
        updated_at=model.updated_at,
        has_unread_messages=model.has_unread_messages,
        messages=messages,
    ), warnings


def _calendar_event(model: CalendarEvent) -> CalendarEventSummary:
    return CalendarEventSummary(id=model.id, start_time=model.start_time, end_time=model.end_time)


def project_calendar(
    model: VisitsCalendarResponse, *, offset: int = 0, limit: int = 25
) -> tuple[CalendarData, list[str]]:
    return CalendarData(
        page=page(model.events, project=_calendar_event, offset=offset, limit=limit),
    ), ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]


def project_credits(model: MemberCredits) -> tuple[CreditsData, list[str]]:
    return CreditsData(
        home_id=model.home_id,
        total_available=model.total_available,
        handyman_hourly_rate_cents=model.handyman_hourly_rate_cents,
    ), []


def project_mailbox(model: MailboxOverviewResponse) -> tuple[MailboxData, list[str]]:
    if model.mailbox is None:
        return MailboxData(mailbox=None), []
    mailbox = model.mailbox
    return MailboxData(
        mailbox=MailboxSummary(
            id=mailbox.id,
            status=mailbox.status,
            onboarding_status=mailbox.onboarding_status,
            claimed_at=mailbox.claimed_at,
            auto_archive_days=mailbox.auto_archive_days,
        )
    ), []


def _mail_item(
    model: MailboxMailItem, *, include_summary: bool, warnings: list[str]
) -> MailItemSummary:
    return MailItemSummary(
        id=model.id,
        scan_status=model.scan_status,
        received_at=model.received_at,
        archived_at=model.archived_at,
        read_at=model.read_at,
        forward_status=model.forward_status,
        shred_status=model.shred_status,
        deposit_status=model.deposit_status,
        summary=_optional_clip(model.summary, 2000, warnings) if include_summary else None,
    )


def project_mail_items(
    model: MailboxMailItemsResponse,
    *,
    include_summary: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[MailItemsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return MailItemsData(
        page=page(
            model.mail_items,
            project=lambda item: _mail_item(
                item, include_summary=include_summary, warnings=warnings
            ),
            offset=offset,
            limit=limit,
        )
    ), warnings


def _package(model: PackageItem, warnings: list[str]) -> PackageSummary:
    return PackageSummary(
        id=model.id,
        name=_optional_clip(model.name, 256, warnings),
        carrier_id=model.carrier_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        status=model.status,
        status_detail=_clip(model.status_detail, 2000, warnings),
        direction=str(model.direction),
        archived=model.archived,
        is_pickup=model.is_pickup,
        est_delivery_date=model.est_delivery_date,
        pickup_status=None if model.pickup_status is None else str(model.pickup_status),
    )


def project_packages(
    model: PackagesResponse, *, offset: int = 0, limit: int = 25
) -> tuple[PackagesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PackagesData(
        page=page(
            model.packages,
            project=lambda item: _package(item, warnings),
            offset=offset,
            limit=limit,
        )
    ), warnings
