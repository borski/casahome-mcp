"""Synthetic projection contracts. Socket access is rejected for every test."""

import socket
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Never, cast

import pytest
from casahome.models.bootstrap import HomeBadgeCounts
from casahome.models.calendar import CalendarEvent, VisitsCalendarResponse
from casahome.models.credits import MemberCredits
from casahome.models.enums import PackageDirection, RequestType, SenderRole, WeatherCondition
from casahome.models.home import HomeDetailsResponse, WeatherResponse
from casahome.models.mailbox import (
    MailboxMailItemsResponse,
    MailboxOverviewResponse,
    PackagesResponse,
)
from casahome.models.requests import RequestCard, RequestDetails, RequestsResponse
from pydantic import ValidationError

from casahome_mcp.outputs import (
    BadgeData,
    CalendarData,
    CalendarEventSummary,
    CreditsData,
    EntityPropertySummary,
    EntitySummary,
    HomesData,
    HomeSummary,
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
    StatusData,
    StorySummary,
    TodoSummary,
    ToolResponse,
    WeatherData,
)
from casahome_mcp.projections import (
    ProjectionError,
    page,
    project_badges,
    project_calendar,
    project_credits,
    project_inventory,
    project_mail_items,
    project_mailbox,
    project_packages,
    project_request,
    project_requests,
    project_weather,
)

PRIVATE = "synthetic-sensitive-extra-never-project"
COMPLETENESS = "UPSTREAM_COMPLETENESS_UNKNOWN"


@pytest.fixture(autouse=True)
def reject_socket_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args: object, **kwargs: object) -> Never:
        raise AssertionError("Socket access is forbidden in projection tests.")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)


def _inventory(count: int = 1) -> HomeDetailsResponse:
    return HomeDetailsResponse.model_validate(
        {
            "home": {
                "id": "synthetic-home",
                "display_address": PRIVATE,
                "password": PRIVATE,
                "stories": [
                    {
                        "id": "story-one",
                        "name": "First floor",
                        "floor_number": -1,
                        "payment": PRIVATE,
                        "rooms": [
                            {
                                "id": "room-one",
                                "name": "Kitchen",
                                "image_url": PRIVATE,
                                "password": PRIVATE,
                                "room_properties": [
                                    {
                                        "id": "property",
                                        "definition_id": "definition",
                                        "title": PRIVATE,
                                        "key": "secret",
                                        "value": {"password": PRIVATE},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "entities": [
                {
                    "id": f"entity-{index}",
                    "category_id": "category-one",
                    "category": "Appliance",
                    "status": "future-inventory-status",
                    "rooms": ["room-one"],
                    "stories": ["story-one"],
                    "make": {"id": "make-one", "name": "Example make", "password": PRIVATE},
                    "model": {"id": "model-one", "name": "Example model", "password": PRIVATE},
                    "manuals": [{"download_url": PRIVATE}],
                    "thumbnail_url": PRIVATE,
                    "password": PRIVATE,
                }
                for index in range(count)
            ],
            "room_entity_map": {PRIVATE: [PRIVATE]},
            "associated_entities": {PRIVATE: [PRIVATE]},
            "password": PRIVATE,
        }
    )


def _card(identifier: str, title: str = "Fix a fixture") -> RequestCard:
    return RequestCard.model_validate(
        {
            "id": identifier,
            "type": "future-request-type",
            "title": title,
            "emoji": PRIVATE,
            "updated_at": 1234567890123,
            "has_unread_messages": True,
            "pending_invoice_count": 2,
            "pending_purchase_count": 3,
            "pending_schedule_prompt_count": 4,
            "concierge_awaiting_reply": True,
            "latest_message_preview": PRIVATE,
            "vendor_visits": [{"password": PRIVATE}],
            "status": PRIVATE,
            "password": PRIVATE,
        }
    )


def _requests() -> RequestsResponse:
    return RequestsResponse.model_validate(
        {
            "requests": {
                "needs_review": [_card("review"), _card("repeated")],
                "completed_count": 19,
                "completed": {"title": PRIVATE},
                "sections": [
                    {
                        "name": "section-b",
                        "title": "Second",
                        "count": 88,
                        "items": [_card("repeated"), _card("second")],
                    },
                    {"name": "section-a", "title": "First", "items": [_card("first")]},
                ],
                "password": PRIVATE,
            },
            "tasks": {
                "sections": [
                    {
                        "name": "tasks",
                        "title": PRIVATE,
                        "items": [{"password": PRIVATE}],
                    }
                ]
            },
            "todos": {
                "sections": [
                    {
                        "name": "todo-section",
                        "title": "To do",
                        "items": [
                            {
                                "id": "todo-one",
                                "kind": "future-todo-kind",
                                "title": "Todo title",
                                "emoji": PRIVATE,
                                "updated_at": 9,
                                "state": "future-todo-state",
                                "origin_todo_id": "origin-one",
                                "password": PRIVATE,
                            }
                        ],
                        "password": PRIVATE,
                    }
                ]
            },
            "password": PRIVATE,
        }
    )


def _request() -> RequestDetails:
    return RequestDetails.model_validate(
        {
            "id": "request-one",
            "type": "future-request-type",
            "status": "future-request-status",
            "title": "A request",
            "emoji": PRIVATE,
            "created_at": 123,
            "updated_at": 456,
            "summary": {"password": PRIVATE},
            "invoices": [{"payment": PRIVATE}],
            "purchases": [PRIVATE],
            "feedback": {"secret": PRIVATE},
            "visits": [PRIVATE],
            "messages": [
                {
                    "id": "message-one",
                    "created_at": 789,
                    "sender_role": "future-role",
                    "sender_name": "Synthetic sender",
                    "content": "Untrusted narrative",
                    "attachments": [{"signed_url": PRIVATE}],
                    "invoice": {"payment": PRIVATE},
                    "scheduling_prompt": {"secret": PRIVATE},
                    "availability_request": {"secret": PRIVATE},
                    "purchase_approval_requests": [PRIVATE],
                    "password": PRIVATE,
                },
                {
                    "id": "message-two",
                    "created_at": 790,
                    "sender_role": SenderRole.MEMBER,
                    "sender_name": "Another sender",
                    "content": None,
                },
            ],
            "password": PRIVATE,
        }
    )


def _mail_items() -> MailboxMailItemsResponse:
    return MailboxMailItemsResponse.model_validate(
        {
            "mail_items": [
                {
                    "id": "mail-one",
                    "scan_status": "future-scan-status",
                    "received_at": "raw-received-timestamp",
                    "archived_at": "raw-archived-timestamp",
                    "read_at": "raw-read-timestamp",
                    "forward_status": "future-forward-status",
                    "shred_status": "future-shred-status",
                    "deposit_status": "future-deposit-status",
                    "summary": "Optional mail narrative",
                    "envelope_image_url": PRIVATE,
                    "sender": PRIVATE,
                    "addressed_to": PRIVATE,
                    "forward_tracking_number": PRIVATE,
                    "check_details": {"password": PRIVATE},
                    "password": PRIVATE,
                }
            ],
            "password": PRIVATE,
        }
    )


def _packages() -> PackagesResponse:
    return PackagesResponse.model_validate(
        {
            "next_pickup_lockdown": 1,
            "next_pickup_start": 2,
            "next_pickup_end": 3,
            "package_tracking_inbound_email": PRIVATE,
            "next_pickup_item_ids": [PRIVATE],
            "password": PRIVATE,
            "packages": [
                {
                    "id": "package-one",
                    "name": "Synthetic package",
                    "carrier_id": "carrier-one",
                    "created_at": 10,
                    "updated_at": 11,
                    "status": "future-status",
                    "status_detail": "Untrusted package narrative",
                    "direction": "future-direction",
                    "archived": True,
                    "is_pickup": True,
                    "est_delivery_date": 12,
                    "pickup_status": "future-pickup-status",
                    "tracking_number": PRIVATE,
                    "pickup_qr_code": PRIVATE,
                    "pickup_image_url": PRIVATE,
                    "purchased_item": {"password": PRIVATE},
                    "signed_by": PRIVATE,
                    "password": PRIVATE,
                }
            ],
        }
    )


def _assert_private(model: OutputModel) -> None:
    assert PRIVATE not in model.model_dump_json()


def test_socket_guard_negative_control() -> None:
    with socket.socket() as sock, pytest.raises(AssertionError, match="Socket access"):
        sock.connect(("127.0.0.1", 1))


@pytest.mark.parametrize(
    "dto",
    [
        OutputModel,
        ToolResponse[BadgeData],
        Page[HomeSummary],
        StatusData,
        HomeSummary,
        HomesData,
        BadgeData,
        WeatherData,
        RoomSummary,
        EntitySummary,
        EntityPropertySummary,
        InventoryData,
        InventoryItemData,
        RequestCardSummary,
        TodoSummary,
        RequestsData,
        MessageSummary,
        RequestData,
        CalendarEventSummary,
        CalendarData,
        CreditsData,
        MailboxSummary,
        MailboxData,
        MailItemSummary,
        MailItemsData,
        PackageSummary,
        PackagesData,
    ],
)
def test_every_dto_is_strict_and_forbids_extras(dto: type[OutputModel]) -> None:
    assert dto.model_config["strict"] is True
    assert dto.model_config["extra"] == "forbid"
    assert dto.model_json_schema()["additionalProperties"] is False
    with pytest.raises(ValidationError) as error:
        dto.model_validate({"unexpected": PRIVATE})
    assert any(item["type"] == "extra_forbidden" for item in error.value.errors())
    assert PRIVATE not in str(error.value)


@pytest.mark.parametrize("invalid", ["1", 1.0, True, None])
def test_numeric_dto_fields_reject_coercion(invalid: object) -> None:
    for field in ("total_available", "handyman_hourly_rate_cents"):
        values: dict[str, object] = {
            "home_id": "synthetic-home",
            "total_available": 1,
            "handyman_hourly_rate_cents": 2,
        }
        values[field] = invalid
        with pytest.raises(ValidationError):
            CreditsData.model_validate(values)


def test_envelope_has_exact_fields_and_normalizes_aware_time() -> None:
    data = BadgeData(computed_at=1, total=2, features={})
    fetched_at = datetime(2000, 1, 1, tzinfo=timezone(timedelta(hours=2)))
    response = ToolResponse[BadgeData](
        source="casa",
        confidence="UNVERIFIED",
        home_id="synthetic-home",
        fetched_at=fetched_at,
        warnings=[],
        data=data,
    )
    assert response.fetched_at == fetched_at.astimezone(UTC)
    assert response.fetched_at is not None and response.fetched_at.tzinfo is UTC
    assert set(response.model_dump()) == {
        "source",
        "confidence",
        "home_id",
        "fetched_at",
        "warnings",
        "data",
    }
    with pytest.raises(ValidationError, match="timezone-aware"):
        ToolResponse[BadgeData](
            source="casa",
            confidence="UNVERIFIED",
            home_id=None,
            fetched_at=datetime(2000, 1, 1),
            warnings=[],
            data=data,
        )
    local = ToolResponse[BadgeData](
        source="configuration",
        confidence="LOCAL",
        home_id=None,
        fetched_at=None,
        warnings=[],
        data=data,
    )
    assert local.model_dump()["fetched_at"] is None


def test_nested_envelope_extras_and_wrong_data_are_rejected() -> None:
    values: dict[str, object] = {
        "source": "casa",
        "confidence": "UNVERIFIED",
        "home_id": None,
        "fetched_at": None,
        "warnings": [],
        "data": {"computed_at": 1, "total": 1, "features": {}, "password": PRIVATE},
    }
    with pytest.raises(ValidationError):
        ToolResponse[BadgeData].model_validate(values)
    values["data"] = {"computed_at": 1, "total": "1", "features": {}}
    with pytest.raises(ValidationError):
        ToolResponse[BadgeData].model_validate(values)


def test_local_status_and_home_contracts() -> None:
    status = StatusData(
        version="synthetic",
        mode="read_only",
        token_configured=False,
        configured_home_count=1,
        allow_unverified_reads=False,
        refresh_token_rotated=False,
        disabled_features=["weather"],
    )
    assert set(status.model_dump()) == {
        "version",
        "mode",
        "token_configured",
        "configured_home_count",
        "allow_unverified_reads",
        "allow_actions",
        "allow_messages",
        "allow_uploads",
        "allow_unverified_actions",
        "refresh_token_rotated",
        "disabled_features",
    }
    homes = HomesData(homes=[HomeSummary(id="synthetic-home", label="Synthetic home")])
    assert homes.model_dump() == {"homes": [{"id": "synthetic-home", "label": "Synthetic home"}]}


def test_badges_preserve_keys_values_and_raw_timestamp_without_extras() -> None:
    keys = {"a" * 127 + "x": 1, "a" * 127 + "y": 2, "": 0, "UNKNOWN/Feature": -1}
    model = HomeBadgeCounts.model_validate(
        {
            "computed_at": 1234567890123,
            "total": 3,
            "features": keys,
            "password": PRIVATE,
        }
    )
    data, warnings = project_badges(model)
    assert data.model_dump() == {"computed_at": 1234567890123, "total": 3, "features": keys}
    assert warnings == []
    data.features["new"] = 4
    assert "new" not in model.features
    _assert_private(data)


@pytest.mark.parametrize(
    "features",
    [
        {str(index): index for index in range(101)},
        {"x" * 129: 1},
    ],
)
def test_badge_overflows_raise_code_only(features: dict[str, int]) -> None:
    with pytest.raises(ProjectionError) as error:
        project_badges(HomeBadgeCounts(computed_at=0, total=0, features=features))
    assert error.value.code == "OUTPUT_TOO_LARGE"
    assert str(error.value) == "OUTPUT_TOO_LARGE"


def test_badge_boundary_of_one_hundred_entries() -> None:
    data, _ = project_badges(
        HomeBadgeCounts(
            computed_at=0,
            total=100,
            features={str(index): 1 for index in range(100)},
        )
    )
    assert len(data.features) == 100


@pytest.mark.parametrize("condition", [WeatherCondition.CLEAR, "future-weather-condition"])
def test_weather_keeps_enum_values_and_nulls(condition: str) -> None:
    model = WeatherResponse.model_validate(
        {
            "temperature_degrees": 12.5,
            "temperature_units": "future-units",
            "condition_type": condition,
            "sunrise_at": 1234567890123,
            "password": PRIVATE,
        }
    )
    data, warnings = project_weather(model)
    assert data.model_dump() == {
        "temperature_degrees": 12.5,
        "temperature_units": "future-units",
        "condition_type": str(condition),
        "sunrise_at": 1234567890123,
        "sunset_at": None,
    }
    assert warnings == []
    _assert_private(data)


def test_inventory_entities_project_typed_make_model_without_extras() -> None:
    data, warnings = project_inventory(_inventory())
    assert data.kind == "entities"
    assert data.page.items[0].model_dump() == {
        "id": "entity-0",
        "category_id": "category-one",
        "category": "Appliance",
        "status": "future-inventory-status",
        "type_id": None,
        "type": None,
        "rooms": ["room-one"],
        "stories": ["story-one"],
        "make": "Example make",
        "model": "Example model",
        "serial_number": None,
        "identity_state": None,
        "properties": [],
        "model_summary": None,
    }
    assert warnings == [COMPLETENESS]
    _assert_private(data)


def test_inventory_rooms_keep_story_context_and_source_order() -> None:
    model = _inventory()
    model.home.stories.append(model.home.stories[0].model_copy(update={"id": "story-two"}))
    data, warnings = project_inventory(model, kind="rooms", offset=1, limit=1)
    assert data.kind == "rooms"
    assert data.page.total_in_response == 2
    assert data.page.items[0].model_dump() == {
        "id": "room-one",
        "name": "Kitchen",
        "story_id": "story-two",
        "story_name": "First floor",
        "floor_number": -1,
        "room_type_id": None,
    }
    assert warnings == [COMPLETENESS]
    _assert_private(data)


def test_story_readback_includes_empty_stories_and_rejects_unsafe_names() -> None:
    model = _inventory()
    model.home.stories.append(
        model.home.stories[0].model_copy(update={"id": "empty-story", "name": "Empty", "rooms": []})
    )
    stories, warnings = project_inventory(model, kind="stories")
    assert all(isinstance(item, StorySummary) for item in stories.page.items)
    counts = [item.room_count for item in stories.page.items if isinstance(item, StorySummary)]
    assert counts == [1, 0]
    assert warnings == [COMPLETENESS]
    assert all(
        item.story_metadata_complete
        for item in stories.page.items
        if isinstance(item, StorySummary)
    )
    model.home.stories[0].name = "https://example.invalid/private"
    stories, warnings = project_inventory(model, kind="stories")
    first = stories.page.items[0]
    assert isinstance(first, StorySummary)
    assert first.name is None and first.story_metadata_complete is False
    assert "STORY_NAME_OMITTED" in warnings
    assert "example.invalid" not in stories.model_dump_json()


def test_nested_id_lists_are_capped_but_identities_are_never_clipped() -> None:
    model = _inventory()
    long_id = "identity" * 400
    entity = model.entities[0]
    entity.id = long_id
    entity.category_id = long_id
    entity.type_id = long_id
    entity.rooms = [long_id] * 101
    entity.stories = [long_id] * 102
    data, warnings = project_inventory(model)
    item = data.page.items[0]
    assert isinstance(item, EntitySummary)
    assert item.id == item.category_id == item.type_id == long_id
    assert item.rooms == item.stories == [long_id] * 100
    assert warnings == [COMPLETENESS, "NESTED_COLLECTION_TRUNCATED"]
    assert len(entity.rooms) == 101


def test_request_cards_flatten_needs_review_first_and_keep_duplicate_memberships() -> None:
    data, warnings = project_requests(_requests())
    assert data.completed_count == 19
    assert [item.id for item in data.page.items] == [
        "review",
        "repeated",
        "repeated",
        "second",
        "first",
    ]
    assert [item.section_name for item in data.page.items] == [
        "needs_review",
        "needs_review",
        "section-b",
        "section-b",
        "section-a",
    ]
    assert [item.section_title for item in data.page.items] == [
        None,
        None,
        "Second",
        "Second",
        "First",
    ]
    card = data.page.items[0]
    assert isinstance(card, RequestCardSummary)
    assert card.type == "future-request-type"
    assert card.pending_invoice_count == 2
    assert card.pending_purchase_count == 3
    assert card.pending_schedule_prompt_count == 4
    assert card.has_unread_messages and card.concierge_awaiting_reply
    assert "status" not in card.model_dump()
    assert warnings == [COMPLETENESS]
    _assert_private(data)


def test_todos_keep_unknown_enum_strings_and_do_not_claim_completed_count() -> None:
    data, warnings = project_requests(_requests(), lane="todos")
    assert data.completed_count is None
    assert data.page.items[0].model_dump() == {
        "kind": "future-todo-kind",
        "id": "todo-one",
        "title": "Todo title",
        "updated_at": 9,
        "state": "future-todo-state",
        "origin_todo_id": "origin-one",
        "section_name": "todo-section",
        "section_title": "To do",
    }
    assert warnings == [COMPLETENESS]
    _assert_private(data)


def test_absent_todos_and_empty_todos_are_distinct() -> None:
    model = _requests()
    model.todos = None
    absent, warnings = project_requests(model, lane="todos")
    assert absent.completed_count is None
    assert absent.page.items == []
    assert absent.page.total_in_response == 0
    assert warnings == [COMPLETENESS, "TODOS_LANE_ABSENT"]
    model = RequestsResponse.model_validate({"requests": {}, "tasks": {}, "todos": {}})
    empty, warnings = project_requests(model, lane="todos")
    assert empty.page.items == []
    assert warnings == [COMPLETENESS]


def test_request_detail_omits_message_text_until_requested() -> None:
    model = _request()
    model.messages[0].content = "x" * 2001
    data, warnings = project_request(model, offset=10**20, limit=100)
    assert data.model_dump() == {
        "id": "request-one",
        "type": "future-request-type",
        "status": "future-request-status",
        "title": "A request",
        "created_at": 123,
        "updated_at": 456,
        "has_unread_messages": False,
        "messages": None,
    }
    assert warnings == []
    assert "x" * 100 not in data.model_dump_json()
    _assert_private(data)


def test_requested_message_page_preserves_nulls_and_filters_nested_extras() -> None:
    data, warnings = project_request(_request(), include_messages=True, offset=0, limit=1)
    assert data.messages is not None
    assert data.messages.total_in_response == 2
    assert data.messages.next_offset == 1
    assert data.messages.items[0].model_dump() == {
        "id": "message-one",
        "created_at": 789,
        "sender_role": "future-role",
        "sender_name": "Synthetic sender",
        "content": "Untrusted narrative",
    }
    assert warnings == [COMPLETENESS]
    _assert_private(data)
    data, _ = project_request(_request(), include_messages=True, offset=1)
    assert data.messages is not None
    assert data.messages.items[0].content is None
    assert data.messages.items[0].sender_role == "member"


def test_requested_empty_messages_is_an_empty_page_not_null() -> None:
    model = _request()
    model.messages = []
    data, warnings = project_request(model, include_messages=True)
    assert data.messages is not None
    assert data.messages.items == []
    assert data.messages.total_in_response == 0
    assert warnings == [COMPLETENESS]


def test_calendar_preserves_raw_integer_timestamps_and_omits_kind() -> None:
    model = VisitsCalendarResponse.model_validate(
        {
            "events": [
                {
                    "id": "event-one",
                    "start_time": 1234567890123,
                    "end_time": 4,
                    "kind": {"vendor_name": PRIVATE},
                    "password": PRIVATE,
                }
            ],
            "password": PRIVATE,
        }
    )
    data, warnings = project_calendar(model)
    assert data.page.items[0].model_dump() == {
        "id": "event-one",
        "start_time": 1234567890123,
        "end_time": 4,
    }
    assert warnings == [COMPLETENESS, "TIMESTAMP_UNITS_UNVERIFIED"]
    _assert_private(data)


def test_credits_preserve_integer_amounts_without_history_or_invented_currency() -> None:
    model = MemberCredits.model_validate(
        {
            "home_id": "synthetic-home",
            "total_available": -5,
            "handyman_hourly_rate_cents": 12000,
            "credits_history": [
                {"id": PRIVATE, "issued_at": 1, "amount": 2, "available_amount": 1}
            ],
            "consumption_history": [{"id": PRIVATE, "date": 1, "consumed_amount": 1}],
            "password": PRIVATE,
        }
    )
    data, warnings = project_credits(model)
    assert data.model_dump() == {
        "home_id": "synthetic-home",
        "total_available": -5,
        "handyman_hourly_rate_cents": 12000,
    }
    assert warnings == []
    _assert_private(data)


def test_nullable_mailbox_and_metadata_only_projection() -> None:
    data, warnings = project_mailbox(MailboxOverviewResponse())
    assert data.model_dump() == {"mailbox": None}
    assert warnings == []
    model = MailboxOverviewResponse.model_validate(
        {
            "mailbox": {
                "id": "mailbox-one",
                "status": "future-mailbox-status",
                "onboarding_status": "future-onboarding-status",
                "claimed_at": "raw-claimed-timestamp",
                "auto_archive_days": None,
                "address": {
                    "line1": PRIVATE,
                    "city": PRIVATE,
                    "state": PRIVATE,
                    "postal_code": PRIVATE,
                },
                "quota": {"month": PRIVATE, "used": 1, "included": 2, "overage_rate_usd_cents": 3},
                "recipients": [{"id": PRIVATE, "kind": PRIVATE, "first_name": PRIVATE}],
                "password": PRIVATE,
            },
            "plan": {"monthly_piece_quota": 1, "overage_rate_usd_cents": 2},
            "password": PRIVATE,
        }
    )
    data, warnings = project_mailbox(model)
    assert data.mailbox is not None
    assert data.mailbox.model_dump() == {
        "id": "mailbox-one",
        "status": "future-mailbox-status",
        "onboarding_status": "future-onboarding-status",
        "claimed_at": "raw-claimed-timestamp",
        "auto_archive_days": None,
    }
    assert warnings == []
    _assert_private(data)


def test_mail_items_summary_is_opt_in_and_timestamps_stay_strings() -> None:
    model = _mail_items()
    data, warnings = project_mail_items(model)
    assert data.page.items[0].model_dump() == {
        "id": "mail-one",
        "scan_status": "future-scan-status",
        "received_at": "raw-received-timestamp",
        "archived_at": "raw-archived-timestamp",
        "read_at": "raw-read-timestamp",
        "forward_status": "future-forward-status",
        "shred_status": "future-shred-status",
        "deposit_status": "future-deposit-status",
        "summary": None,
    }
    assert "Optional mail narrative" not in data.model_dump_json()
    assert warnings == [COMPLETENESS]
    _assert_private(data)
    data, _ = project_mail_items(model, include_summary=True)
    assert data.page.items[0].summary == "Optional mail narrative"
    _assert_private(data)
    model.mail_items[0].summary = None
    data, _ = project_mail_items(model, include_summary=True)
    assert data.page.items[0].summary is None


def test_packages_omit_tracking_and_qr_details_but_preserve_metadata() -> None:
    model = _packages()
    data, warnings = project_packages(model)
    assert data.page.items[0].model_dump() == {
        "id": "package-one",
        "name": "Synthetic package",
        "carrier_id": "carrier-one",
        "created_at": 10,
        "updated_at": 11,
        "status": "future-status",
        "status_detail": "Untrusted package narrative",
        "direction": "future-direction",
        "archived": True,
        "is_pickup": True,
        "est_delivery_date": 12,
        "pickup_status": "future-pickup-status",
    }
    assert warnings == [COMPLETENESS]
    _assert_private(data)
    model.packages[0].name = None
    model.packages[0].pickup_status = None
    model.packages[0].est_delivery_date = None
    model.packages[0].direction = PackageDirection.INBOUND
    data, _ = project_packages(model)
    assert data.page.items[0].name is None
    assert data.page.items[0].pickup_status is None
    assert data.page.items[0].est_delivery_date is None
    assert data.page.items[0].direction == "inbound"


@pytest.mark.parametrize("offset,limit", [(-1, 25), (0, 0), (0, 101), (True, 25), (0, True)])
def test_every_paginated_projection_checks_bounds_even_when_messages_are_off(
    offset: int, limit: int
) -> None:
    projections: list[Callable[[], tuple[OutputModel, list[str]]]] = [
        lambda: project_inventory(_inventory(), offset=offset, limit=limit),
        lambda: project_inventory(_inventory(), kind="rooms", offset=offset, limit=limit),
        lambda: project_requests(_requests(), offset=offset, limit=limit),
        lambda: project_requests(_requests(), lane="todos", offset=offset, limit=limit),
        lambda: project_request(_request(), offset=offset, limit=limit),
        lambda: project_calendar(VisitsCalendarResponse(), offset=offset, limit=limit),
        lambda: project_mail_items(_mail_items(), offset=offset, limit=limit),
        lambda: project_packages(_packages(), offset=offset, limit=limit),
    ]
    for projection in projections:
        with pytest.raises(ProjectionError) as error:
            projection()
        assert error.value.code == "INVALID_ARGUMENT"
        assert str(error.value) == "INVALID_ARGUMENT"


def test_invalid_kind_and_lane_are_not_silently_substituted() -> None:
    with pytest.raises(ProjectionError, match="INVALID_ARGUMENT"):
        project_inventory(_inventory(), kind=cast(InventoryKind, "future-kind"))
    with pytest.raises(ProjectionError, match="INVALID_ARGUMENT"):
        project_requests(_requests(), lane=cast(RequestLane, "future-lane"))


@pytest.mark.parametrize(
    "offset,expected,next_offset",
    [
        (0, ["event-0", "event-1"], 2),
        (2, ["event-2"], None),
        (3, [], None),
        (4, [], None),
        (10**30, [], None),
    ],
)
def test_page_metadata_is_truthful_at_and_beyond_end(
    offset: int, expected: list[str], next_offset: int | None
) -> None:
    model = VisitsCalendarResponse(
        events=[
            CalendarEvent(id=f"event-{index}", start_time=index, end_time=index + 1)
            for index in range(3)
        ]
    )
    data, _ = project_calendar(model, offset=offset, limit=2)
    assert [item.id for item in data.page.items] == expected
    assert data.page.offset == offset
    assert data.page.returned_count == len(expected)
    assert data.page.total_in_response == 3
    assert data.page.next_offset == next_offset
    assert data.page.has_more_in_response is (next_offset is not None)
    assert data.page.pagination_scope == "single_upstream_response"


def test_page_helper_projects_only_selected_items() -> None:
    observed: list[int] = []

    def project(value: int) -> HomeSummary:
        observed.append(value)
        return HomeSummary(id=str(value), label="Synthetic home")

    result = page([0, 1, 2, 3], project=project, offset=1, limit=2)
    assert observed == [1, 2]
    assert result.next_offset == 3
    assert result.total_in_response == 4


def test_continuation_offsets_above_ten_thousand_are_usable() -> None:
    model = _inventory(10151)
    first, _ = project_inventory(model, offset=10000, limit=100)
    assert first.page.next_offset == 10100
    second, _ = project_inventory(model, offset=first.page.next_offset, limit=100)
    assert second.page.returned_count == 51
    assert second.page.items[0].id == "entity-10100"
    assert second.page.items[-1].id == "entity-10150"
    assert second.page.total_in_response == 10151
    assert second.page.next_offset is None


def test_text_clipping_uses_character_bounds_and_warns_once() -> None:
    model = _request()
    model.title = "界" * 257
    model.messages[0].sender_name = "界" * 257
    model.messages[0].content = "界" * 2001
    data, warnings = project_request(model, include_messages=True)
    assert len(data.title) == 256
    assert data.messages is not None
    message = data.messages.items[0]
    assert len(message.sender_name) == 256
    assert message.content == "界" * 2000
    assert warnings == [COMPLETENESS, "TEXT_TRUNCATED"]
    assert len(model.title) == 257


def test_title_room_and_inventory_labels_are_clipped() -> None:
    model = _inventory()
    model.entities[0].category = "x" * 257
    model.entities[0].type = "x" * 257
    data, warnings = project_inventory(model)
    entity = data.page.items[0]
    assert isinstance(entity, EntitySummary)
    assert len(entity.category) == 256
    assert entity.type == "x" * 256
    assert warnings == [COMPLETENESS, "TEXT_TRUNCATED"]
    model.home.stories[0].name = "x" * 257
    model.home.stories[0].rooms[0].name = "x" * 257
    rooms, warnings = project_inventory(model, kind="rooms")
    room = rooms.page.items[0]
    assert isinstance(room, RoomSummary)
    assert len(room.name) == len(room.story_name) == 256
    assert warnings == [COMPLETENESS, "TEXT_TRUNCATED"]


def test_request_and_todo_titles_clip_but_section_names_and_origin_ids_do_not() -> None:
    model = _requests()
    long_identity = "identity" * 400
    model.requests.needs_review[0].title = "x" * 257
    model.requests.needs_review[0].type = RequestType.CONCIERGE
    model.requests.sections[0].name = long_identity
    model.requests.sections[0].title = "x" * 257
    data, warnings = project_requests(model)
    assert data.page.items[0].title == "x" * 256
    card = data.page.items[0]
    assert isinstance(card, RequestCardSummary)
    assert card.type == "concierge"
    assert data.page.items[2].section_name == long_identity
    assert data.page.items[2].section_title == "x" * 256
    assert warnings == [COMPLETENESS, "TEXT_TRUNCATED"]
    assert model.todos is not None
    model.todos.sections[0].name = long_identity
    model.todos.sections[0].title = "x" * 257
    model.todos.sections[0].items[0].title = "x" * 257
    model.todos.sections[0].items[0].origin_todo_id = long_identity
    data, warnings = project_requests(model, lane="todos")
    todo = data.page.items[0]
    assert isinstance(todo, TodoSummary)
    assert todo.title == todo.section_title == "x" * 256
    assert todo.section_name == todo.origin_todo_id == long_identity
    assert warnings == [COMPLETENESS, "TEXT_TRUNCATED"]


def test_mail_summary_clips_only_when_requested_and_package_text_is_bounded() -> None:
    model = _mail_items()
    model.mail_items[0].summary = "x" * 2001
    data, warnings = project_mail_items(model)
    assert data.page.items[0].summary is None
    assert warnings == [COMPLETENESS]
    data, warnings = project_mail_items(model, include_summary=True)
    assert data.page.items[0].summary == "x" * 2000
    assert warnings == [COMPLETENESS, "TEXT_TRUNCATED"]
    packages = _packages()
    packages.packages[0].name = "x" * 257
    packages.packages[0].status_detail = "x" * 2001
    data_packages, warnings = project_packages(packages)
    assert data_packages.page.items[0].name == "x" * 256
    assert data_packages.page.items[0].status_detail == "x" * 2000
    assert warnings == [COMPLETENESS, "TEXT_TRUNCATED"]


def test_exact_text_and_nested_collection_boundaries_do_not_warn() -> None:
    inventory = _inventory()
    inventory.entities[0].category = "x" * 256
    inventory.entities[0].rooms = ["room"] * 100
    _, warnings = project_inventory(inventory)
    assert warnings == [COMPLETENESS]
    request = _request()
    request.title = "x" * 256
    request.messages[0].content = "x" * 2000
    _, warnings = project_request(request, include_messages=True)
    assert warnings == [COMPLETENESS]


def test_off_page_text_is_not_projected_or_reported_as_truncated() -> None:
    model = _request()
    model.messages[0].content = "x" * 2001
    data, warnings = project_request(model, include_messages=True, offset=1, limit=1)
    assert data.messages is not None
    assert data.messages.items[0].id == "message-two"
    assert warnings == [COMPLETENESS]
