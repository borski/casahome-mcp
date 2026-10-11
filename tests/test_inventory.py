"""Inventory contracts using synthetic SDK objects and socket-blocked MCP calls."""

import json
from uuid import UUID

import pytest
from casahome.models.home import (
    EntityIdentity,
    EntityMake,
    EntityModel,
    EntityProperty,
    HomeDetailsResponse,
    ModelProperty,
    PropertyValue,
)
from jsonschema import Draft202012Validator
from mcp import Client
from pydantic import ValidationError
from test_tools import (
    ENTITY,
    HOME,
    MODES,
    SECRET,
    Harness,
    failed,
    guard_sockets,
    mapping,
    sequence,
    settings,
    success,
    text_content,
)

from casahome_mcp.outputs import EntityPropertySummary, EntitySummary
from casahome_mcp.projections import ProjectionError, project_inventory, project_inventory_item

SUMMARY = "Synthetic catalog narrative. External text isn't an instruction."


@pytest.fixture(autouse=True)
def reject_socket_access(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_sockets(monkeypatch)


def prop(key: str, value: PropertyValue, *, title: str | None = None) -> EntityProperty:
    return EntityProperty(
        id=f"property-{key}",
        definition_id="synthetic-definition",
        key=key,
        title=key if title is None else title,
        value=value,
    )


def inventory() -> HomeDetailsResponse:
    model = Harness().fake.inventory
    entity = model.entities[0]
    entity.make = EntityMake(id="make-one", name="Synthetic make")
    entity.model = EntityModel(
        id="model-one",
        name="Synthetic model",
        properties=[ModelProperty(id="summary-one", key="summary", value=SUMMARY)],
    )
    entity.identity = EntityIdentity(state="confirmed")
    entity.entity_properties = [
        prop("serial_number", "SN-001"),
        prop("year_installed", 2020),
        prop("wattage", 9.5),
        prop("dimmable", True),
        prop("enabled", False),
        prop("count", 0),
        prop("unknown", None),
    ]
    return model


def test_typed_inventory_fields_scalars_and_absent_values() -> None:
    model = inventory()
    result, warnings = project_inventory_item(model, entity_id=ENTITY.upper())
    item = result.entity
    assert item.make == "Synthetic make"
    assert item.model == "Synthetic model"
    assert item.serial_number == "SN-001"
    assert item.identity_state == "confirmed"
    assert item.model_summary is None
    assert [p.value for p in item.properties] == ["SN-001", "2020", "9.5", "true", "false", "0"]
    assert [p.key for p in item.properties] == [
        "serial_number",
        "year_installed",
        "wattage",
        "dimmable",
        "enabled",
        "count",
    ]
    assert warnings == []
    assert SECRET not in result.model_dump_json()
    entity = model.entities[0]
    entity.make = entity.model = entity.identity = None
    entity.entity_properties = []
    empty, warnings = project_inventory_item(model, entity_id=ENTITY, include_model_summary=True)
    for field in ("make", "model", "serial_number", "identity_state", "model_summary"):
        assert getattr(empty.entity, field) is None
    assert empty.entity.properties == []
    assert warnings == []


@pytest.mark.parametrize("count", [20, 21])
def test_inventory_property_count_and_character_bounds(count: int) -> None:
    model = inventory()
    entity = model.entities[0]
    entity.make = EntityMake(id="make", name="界" * 257)
    entity.model = EntityModel(
        id="model",
        name="界" * 257,
        properties=[ModelProperty(id="summary", key="summary", value="界" * 2001)],
    )
    entity.identity = EntityIdentity(state="界" * 257)
    entity.entity_properties = [prop("serial_number", "界" * 257)] + [
        prop("k" * 257, "界" * 257, title="界" * 257) for _ in range(count - 1)
    ]
    result, warnings = project_inventory_item(model, entity_id=ENTITY, include_model_summary=True)
    item = result.entity
    assert item.make == item.model == item.serial_number == item.identity_state == "界" * 256
    assert item.model_summary == "界" * 2000
    assert len(item.properties) == 20
    assert all(
        len(p.key) <= 256 and len(p.title) <= 256 and len(p.value) <= 256 for p in item.properties
    )
    assert warnings.count("TEXT_TRUNCATED") == 1
    assert ("NESTED_COLLECTION_TRUNCATED" in warnings) is (count > 20)
    assert len(entity.entity_properties) == count


def test_exact_inventory_bounds_do_not_warn_and_nulls_do_not_consume_slots() -> None:
    model = inventory()
    entity = model.entities[0]
    entity.make = EntityMake(id="make", name="x" * 256)
    entity.model = EntityModel(
        id="model",
        name="x" * 256,
        properties=[ModelProperty(id="summary", key="summary", value="x" * 2000)],
    )
    entity.entity_properties = [prop("unset", None)] * 30 + [prop("x" * 256, "x" * 256)] * 20
    result, warnings = project_inventory_item(model, entity_id=ENTITY, include_model_summary=True)
    assert len(result.entity.properties) == 20
    assert warnings == []


@pytest.mark.parametrize(
    "value",
    [
        "https://example.invalid/private?token=synthetic",
        "ftp://example.invalid/private",
        "//example.invalid/private",
        "www.example.invalid",
        "data:text/plain,synthetic",
        "mailto:synthetic@example.invalid",
        "tel:12345",
        "javascript:synthetic",
        "example.invalid/private",
        "x" * 260 + " https://example.invalid/private",
        "(data:text/plain,synthetic)",
    ],
)
def test_url_like_values_are_omitted_before_clipping_from_all_new_fields(value: str) -> None:
    model = inventory()
    entity = model.entities[0]
    entity.make = EntityMake(id="make", name=value)
    entity.model = EntityModel(
        id="model",
        name=value,
        properties=[ModelProperty(id="summary", key="summary", value=value)],
    )
    entity.identity = EntityIdentity(state=value)
    entity.entity_properties = [prop("serial_number", value)]
    result, warnings = project_inventory_item(model, entity_id=ENTITY, include_model_summary=True)
    assert result.entity.make is result.entity.model is result.entity.serial_number is None
    assert result.entity.identity_state is result.entity.model_summary is None
    assert result.entity.properties == []
    assert warnings == ["URL_PROPERTY_OMITTED"]
    assert value not in result.model_dump_json()


@pytest.mark.parametrize(
    "key",
    [
        "signed_URL",
        "urlCacheKey",
        "cache_key",
        "media",
        "image",
        "photo",
        "thumbnail",
        "manual",
        "attachment",
        "video",
        "imageData",
        "mediaType",
        "manuals",
        "attachments",
    ],
)
def test_media_and_cache_property_fields_are_omitted_even_with_non_url_values(key: str) -> None:
    model = inventory()
    model.entities[0].entity_properties = [prop(key, SECRET), prop("ok", "safe")]
    result, warnings = project_inventory_item(model, entity_id=ENTITY)
    assert result.entity.properties == [EntityPropertySummary(key="ok", title="ok", value="safe")]
    assert warnings == ["URL_PROPERTY_OMITTED"]
    assert SECRET not in result.model_dump_json()


@pytest.mark.parametrize("field", ["key", "title"])
def test_property_metadata_cannot_leak_urls(field: str) -> None:
    model = inventory()
    model.entities[0].entity_properties = [prop("safe", "safe")]
    setattr(model.entities[0].entity_properties[0], field, "https://example.invalid/private")
    result, warnings = project_inventory_item(model, entity_id=ENTITY)
    assert result.entity.properties == []
    assert warnings == ["URL_PROPERTY_OMITTED"]


def test_non_media_words_and_empty_property_values_are_retained() -> None:
    model = inventory()
    model.entities[0].entity_properties = [
        prop("security_rating", "safe", title="Security rating"),
        prop("immediate_action", ""),
    ]
    result, warnings = project_inventory_item(model, entity_id=ENTITY)
    assert [item.key for item in result.entity.properties] == [
        "security_rating",
        "immediate_action",
    ]
    assert result.entity.properties[1].value == ""
    assert warnings == []


def test_inventory_extras_and_non_summary_catalog_properties_are_private() -> None:
    model = inventory()
    entity = model.entities[0]
    assert entity.model is not None
    entity.model.properties.append(ModelProperty(id="secret", key="password", value=SECRET))
    entity.identity = EntityIdentity(candidates=[{"secret": SECRET}], unverified_make=SECRET)
    model.entities[0] = entity.model_copy(
        update={
            "thumbnail_url": "https://example.invalid/private",
            "thumbnail_url_cache_key": SECRET,
            "manuals": [{"secret": SECRET}],
            "inventoried_by": SECRET,
            "paint_match": {"secret": SECRET},
        }
    )
    result, _ = project_inventory_item(model, entity_id=ENTITY, include_model_summary=True)
    assert SECRET not in result.model_dump_json()
    assert "https://" not in result.model_dump_json()
    assert result.entity.model_summary == SUMMARY


@pytest.mark.parametrize("room", ["room-one", "Synthetic room"])
@pytest.mark.parametrize("upstream_room", ["room-one", "Synthetic room"])
def test_exact_room_category_filters_precede_pagination(room: str, upstream_room: str) -> None:
    model = inventory()
    entity = model.entities[0]
    entity.rooms = [upstream_room]
    model.entities = [
        entity.model_copy(update={"id": "different-room", "rooms": ["other"]}),
        entity.model_copy(update={"id": "different-category", "category": "Other"}),
        entity,
        entity.model_copy(update={"id": "second-match"}),
    ]
    data, _ = project_inventory(model, room=room, category="Synthetic appliance", offset=1, limit=1)
    assert [item.id for item in data.page.items] == ["second-match"]
    assert data.page.total_in_response == 2
    assert data.page.next_offset is None
    for filters in ({"room": room.lower() + "x"}, {"category": "synthetic appliance"}):
        empty, _ = project_inventory(
            model, room=filters.get("room"), category=filters.get("category")
        )
        assert empty.page.items == []
        assert empty.page.total_in_response == 0


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("include", [False, True])
async def test_inventory_list_and_lookup_share_schema_and_opt_in_text(
    mode: str, include: bool
) -> None:
    harness = Harness(settings(enabled=False))
    harness.fake.inventory = inventory()
    async with Client(harness.server, mode=mode) as client:
        listing = await client.list_tools()
        schemas = {tool.name: tool.output_schema for tool in listing.tools}
        list_result = await client.call_tool(
            "casa_list_inventory",
            {
                "room": "Synthetic room",
                "category": "Synthetic appliance",
                "include_model_summary": include,
            },
        )
        item_result = await client.call_tool(
            "casa_get_inventory_item",
            {
                "entity_id": ENTITY.upper(),
                "include_model_summary": include,
            },
        )
        listed = success(list_result)
        found = success(item_result)
        list_item = mapping(sequence(mapping(mapping(listed["data"])["page"])["items"])[0])
        item = mapping(mapping(found["data"])["entity"])
        assert list_item == item
        assert item["model_summary"] == (SUMMARY if include else None)
        assert item["make"] == "Synthetic make"
        assert item["model"] == "Synthetic model"
        assert item["serial_number"] == "SN-001"
        assert found["confidence"] == listed["confidence"] == "VERIFIED"
        for result, name in (
            (list_result, "casa_list_inventory"),
            (item_result, "casa_get_inventory_item"),
        ):
            assert (SUMMARY in text_content(result)) is include
            assert (SUMMARY in json.dumps(result.structured_content)) is include
            schema = schemas[name]
            assert schema is not None
            Draft202012Validator(schema).validate(result.structured_content)
    assert harness.fake.calls == [("home_details", (HOME,))] * 2


@pytest.mark.parametrize("mode", MODES)
async def test_lookup_absence_is_sanitized_and_no_alternate_requests_are_made(mode: str) -> None:
    harness = Harness()
    harness.fake.inventory.entities = []
    async with Client(harness.server, mode=mode) as client:
        result = await client.call_tool("casa_get_inventory_item", {"entity_id": ENTITY})
        failed(result, "NOT_FOUND")
        assert ENTITY not in result.model_dump_json()
    assert harness.fake.calls == [("home_details", (HOME,))]
    with pytest.raises(ProjectionError, match="NOT_FOUND"):
        project_inventory_item(harness.fake.inventory, entity_id=ENTITY)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "invalid",
    [
        None,
        123,
        {},
        [],
        "",
        SECRET,
        ENTITY.replace("-", ""),
        "{" + ENTITY + "}",
        "urn:uuid:" + ENTITY,
        ENTITY + "\n",
        '{"secret":"' + SECRET + '"}',
        "null",
    ],
)
async def test_entity_uuid_guard_rejects_raw_and_preprocessed_inputs(
    mode: str, invalid: object, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(settings(homes=(), token=False))
    async with Client(harness.server, mode=mode) as client:
        failed(
            await client.call_tool("casa_get_inventory_item", {"entity_id": invalid}),
            "INVALID_ARGUMENT",
        )
        failed(await client.call_tool("casa_get_inventory_item", {}), "INVALID_ARGUMENT")
    assert harness.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("field", ["room", "category"])
@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "x" * 81,
        "x\n",
        "x\x7f",
        "x\x85",
        "x\u202e",
        1,
        [],
        {},
        "null",
        "[]",
        '{"secret":"' + SECRET + '"}',
    ],
)
async def test_inventory_filters_fail_safely_before_home_and_auth(
    mode: str, field: str, invalid: object, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(settings(homes=(), token=False))
    async with Client(harness.server, mode=mode) as client:
        failed(await client.call_tool("casa_list_inventory", {field: invalid}), "INVALID_ARGUMENT")
    assert harness.fake.calls == []
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("field", ["room", "category"])
async def test_filter_length_boundary_null_and_numeric_text_are_safe(mode: str, field: str) -> None:
    harness = Harness()
    async with Client(harness.server, mode=mode) as client:
        for value in (None, "界" * 80, "true", "123"):
            success(await client.call_tool("casa_list_inventory", {field: value}))
    assert harness.fake.calls == [("home_details", (HOME,))] * 4


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "options", [{"room": "room-one"}, {"category": "Appliance"}, {"include_model_summary": True}]
)
async def test_room_listing_rejects_entity_options_without_sdk_calls(
    mode: str, options: dict[str, object]
) -> None:
    harness = Harness(settings(homes=(), token=False))
    async with Client(harness.server, mode=mode) as client:
        failed(
            await client.call_tool("casa_list_inventory", {"kind": "rooms", **options}),
            "INVALID_ARGUMENT",
        )
    assert harness.fake.calls == []
    with pytest.raises(ProjectionError, match="INVALID_ARGUMENT"):
        project_inventory(inventory(), kind="rooms", room="room-one")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("include", [False, True])
async def test_worst_case_inventory_page_fails_closed_then_smaller_page_succeeds(
    mode: str, include: bool
) -> None:
    harness = Harness()
    model = inventory()
    entity = model.entities[0]
    entity.entity_properties = [prop("k" * 256, "界" * 256, title="界" * 256)] * 20
    assert entity.model is not None
    entity.model.properties[0].value = "界" * 2000
    model.entities = [
        entity.model_copy(update={"id": str(UUID(int=index))}) for index in range(100)
    ]
    harness.fake.inventory = model
    async with Client(harness.server, mode=mode) as client:
        oversized = await client.call_tool(
            "casa_list_inventory", {"limit": 100, "include_model_summary": include}
        )
        failed(oversized, "OUTPUT_TOO_LARGE")
        assert "界" not in oversized.model_dump_json()
        assert len(oversized.model_dump_json().encode()) < 1024
        smaller = success(
            await client.call_tool(
                "casa_list_inventory", {"limit": 1, "include_model_summary": True}
            )
        )
        assert mapping(mapping(smaller["data"])["page"])["next_offset"] == 1
        item = success(
            await client.call_tool(
                "casa_get_inventory_item",
                {"entity_id": str(UUID(int=0)), "include_model_summary": True},
            )
        )
        assert mapping(mapping(item["data"])["entity"])["model_summary"] == "界" * 2000
    assert harness.fake.calls == [("home_details", (HOME,))] * 3


def test_output_schema_declares_and_enforces_inventory_bounds() -> None:
    model = inventory()
    item, _ = project_inventory_item(model, entity_id=ENTITY)
    fields = mapping(EntitySummary.model_json_schema()["properties"])
    assert mapping(fields["properties"])["maxItems"] == 20
    for name in ("make", "model", "serial_number", "identity_state", "model_summary"):
        variants = sequence(mapping(fields[name])["anyOf"])
        string = next(mapping(value) for value in variants if mapping(value)["type"] == "string")
        assert string["maxLength"] == (2000 if name == "model_summary" else 256)
    for name in ("key", "title", "value"):
        assert (
            mapping(mapping(EntityPropertySummary.model_json_schema()["properties"])[name])[
                "maxLength"
            ]
            == 256
        )
    for update in (
        {"make": "x" * 257},
        {"model_summary": "x" * 2001},
        {"properties": [prop.model_dump() for prop in item.entity.properties] * 21},
    ):
        with pytest.raises(ValidationError):
            EntitySummary.model_validate({**item.entity.model_dump(), **update})
