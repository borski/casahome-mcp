"""Explicit additional read tools. No HTTP passthrough or mutation surface."""

from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from .coverage_outputs import (
    AIBootstrapData,
    AIHistoryData,
    AutopilotPlansData,
    CompletedRequestsData,
    DocumentsData,
    DocumentTypesData,
    NotificationsData,
    OnboardingAvailabilityData,
    OnboardingCalendarData,
    PaintCatalogData,
    PaintColorsData,
    PhotosData,
    PropertyTaxesData,
    PurchasesData,
    RoomImagesData,
    SchedulePreferencesData,
    ServiceHistoryData,
    SuggestedTodosData,
    TodoDetailsData,
    UtilitiesData,
    VehiclesData,
    WorkDocumentSourceData,
)
from .coverage_projections import (
    OPAQUE_CURSOR_PATTERN,
    project_ai_bootstrap,
    project_ai_history,
    project_autopilot_plans,
    project_completed_requests,
    project_document_types,
    project_documents,
    project_notifications,
    project_onboarding_availability,
    project_onboarding_calendar,
    project_paint_brands,
    project_paint_collections,
    project_paint_colors,
    project_paint_search,
    project_photos,
    project_property_taxes,
    project_purchases,
    project_room_images,
    project_schedule_preferences,
    project_service_history,
    project_suggested_todos,
    project_todo_details,
    project_utilities,
    project_vehicles,
    project_work_document_source,
)
from .errors import failure
from .outputs import ToolResponse
from .runtime import AppContext
from .tools import EntityId, HomeId, Limit, Offset, RequestId, describe, read, resolve_home

PositivePage = Annotated[int, Field(ge=1, strict=True, description="Upstream SDK page number.")]
PageSize = Annotated[
    int, Field(ge=1, le=100, strict=True, description="Upstream page size, maximum 100.")
]
OptionalEntityId = Annotated[
    str | None,
    Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
]
OptionalPathId = Annotated[str | None, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Query = Annotated[
    str, Field(min_length=1, max_length=256, description="Search text, no control characters.")
]
OptionalQuery = Annotated[str | None, Field(min_length=1, max_length=256)]
Cursor = Annotated[
    str | None,
    Field(
        pattern=OPAQUE_CURSOR_PATTERN,
        description="Opaque SDK pagination cursor. Not a URL or credential.",
    ),
]
CatalogId = (
    Annotated[int, Field(ge=0, strict=True)]
    | Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
)
OptionalLimit = Annotated[int | None, Field(ge=1, le=100, strict=True)]


def register_coverage_tools(server: MCPServer) -> None:
    remote = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
    )

    @server.tool(
        description=describe(
            "Suggested todos. Prepared brief requires include_brief=true. "
            "No acceptance or creation.",
            "casa_list_suggested_todos",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_suggested_todos(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_brief: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[SuggestedTodosData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "suggested_todos",
            lambda api, home: api.suggested_todos(home),
            lambda value: project_suggested_todos(
                value, include_brief=include_brief, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "One todo's metadata. Prepared brief requires include_brief=true. "
            "Attachments and original text omitted.",
            "casa_get_todo",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_todo(
        todo_id: RequestId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_brief: bool = False,
    ) -> ToolResponse[TodoDetailsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "todo_details",
            lambda api, home: api.todo_details(home, todo_id),
            lambda value: project_todo_details(value, include_brief=include_brief),
        )

    @server.tool(
        description=describe(
            "Completed requests. page/page_size are SDK pagination. offset/limit slice "
            "that response. Search and other-page semantics unverified.",
            "casa_list_completed_requests",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_completed_requests(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        page: PositivePage = 1,
        page_size: PageSize = 100,
        search: OptionalQuery = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[CompletedRequestsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "completed_requests",
            lambda api, home: api.completed_requests(home, page, page_size, search),
            lambda value: project_completed_requests(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Eligible and ineligible maintenance plans with category, pricing, duration "
            "and enabled flags. No signed illustrations or plan changes.",
            "casa_list_autopilot_plans",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_autopilot_plans(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[AutopilotPlansData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "autopilot_plans",
            lambda api, home: api.autopilot_plans(home),
            lambda value: project_autopilot_plans(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Service history for an entity, room or selected home. Non-home targets "
            "require a UUID. Entity-target behavior unverified.",
            "casa_get_inventory_service_history",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_inventory_service_history(
        ctx: Context[AppContext],
        target_type: Literal["entity", "room", "home"] = "home",
        target_id: OptionalEntityId = None,
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[ServiceHistoryData]:
        if target_type != "home" and target_id is None:
            raise failure("INVALID_ARGUMENT")

        app = ctx.request_context.lifespan_context
        if target_type == "home":
            selected_id = resolve_home(app, home_id)
            if target_id is not None and target_id.lower() != selected_id:
                raise failure("HOME_NOT_ALLOWED")
        else:
            assert target_id is not None
            selected_id = target_id

        return await read(
            app,
            home_id,
            "inventory_service_history",
            lambda api, home: api.inventory_service_history(home, target_type, selected_id),
            lambda value: project_service_history(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Document metadata only. SDK cursor and upstream_limit are distinct from local "
            "offset/limit. Query behavior unverified. Excerpts use casa_get_work_document_source.",
            "casa_list_documents",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_documents(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        cursor: Cursor = None,
        upstream_limit: PageSize = 30,
        q: OptionalQuery = None,
        document_type: OptionalPathId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[DocumentsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "documents",
            lambda api, home: api.documents(
                home, cursor=cursor, limit=upstream_limit, q=q, document_type=document_type
            ),
            lambda value: project_documents(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Document type catalog and file size/count/mimetype limits. No upload.",
            "casa_list_document_types",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_document_types(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[DocumentTypesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "document_types",
            lambda api, home: api.document_types(home),
            lambda value: project_document_types(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Work document metadata and citation page labels. Exactly one todo/task/request ID. "
            "Excerpts require include_excerpts=true. Task/request selectors unverified. No URLs.",
            "casa_get_work_document_source",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_work_document_source(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        todo_id: OptionalPathId = None,
        task_id: OptionalPathId = None,
        request_id: OptionalPathId = None,
        include_excerpts: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[WorkDocumentSourceData]:
        if sum(value is not None for value in (todo_id, task_id, request_id)) != 1:
            raise failure("INVALID_ARGUMENT")
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "work_document_source",
            lambda api, home: api.work_document_source(
                home, todo_id=todo_id, task_id=task_id, request_id=request_id
            ),
            lambda value: project_work_document_source(
                value, include_excerpts=include_excerpts, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Search paint names, brands, collections and hex colors. Bounded local results.",
            "casa_search_paint",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_search_paint(
        q: Query,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PaintColorsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "paint_search",
            lambda api, home: api.paint_search(home, q),
            lambda value: project_paint_search(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe("Paint brands and color counts.", "casa_list_paint_brands"),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_paint_brands(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PaintCatalogData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "paint_brands",
            lambda api, home: api.paint_brands(home),
            lambda value: project_paint_brands(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Paint collections and color counts by integer or safe string brand ID, not UUID.",
            "casa_list_paint_collections",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_paint_collections(
        brand_id: CatalogId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PaintCatalogData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "paint_collections",
            lambda api, home: api.paint_collections(home, brand_id),
            lambda value: project_paint_collections(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Paint color IDs, names, brand/collection names and hex "
            "by integer or safe string collection ID.",
            "casa_list_paint_colors",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_paint_colors(
        collection_id: CatalogId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PaintColorsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "paint_colors",
            lambda api, home: api.paint_colors(home, collection_id),
            lambda value: project_paint_colors(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Scheduling day/window labels and enabled flags. No changes.",
            "casa_get_schedule_preferences",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_schedule_preferences(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[SchedulePreferencesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "schedule_preferences",
            lambda api, home: api.schedule_preferences(home),
            lambda value: project_schedule_preferences(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Notification group/type/channel metadata and enabled/required flags. "
            "No arbitrary settings blobs or changes.",
            "casa_get_notification_settings",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_notification_settings(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[NotificationsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "notification_settings",
            lambda api, home: api.notification_settings(home),
            lambda value: project_notifications(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Casa AI conversation and message metadata. Message text and starter prompts "
            "require include_messages=true. Unknown parts omitted. "
            "GET only, not device bootstrap, send or SSE.",
            "casa_get_ai_bootstrap",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_ai_bootstrap(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_messages: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[AIBootstrapData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "casa_ai_bootstrap",
            lambda api, home: api.casa_ai_bootstrap(home),
            lambda value: project_ai_bootstrap(
                value, include_messages=include_messages, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Casa AI history. Text requires include_messages=true. before/upstream_limit "
            "are SDK query controls, unverified semantics. offset/limit slice one response. "
            "Unknown parts omitted.",
            "casa_list_ai_history",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_ai_history(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        before: Cursor = None,
        upstream_limit: OptionalLimit = None,
        include_messages: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[AIHistoryData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "casa_ai_messages",
            lambda api, home: api.casa_ai_messages(home, limit=upstream_limit, before=before),
            lambda value: project_ai_history(
                value, include_messages=include_messages, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Vehicle IDs, names, make/model/year/status and powertrain. "
            "No VIN, location, raw telemetry or control.",
            "casa_list_vehicles",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_vehicles(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[VehiclesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "vehicles",
            lambda api, home: api.vehicles(home),
            lambda value: project_vehicles(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Utility service types/units/counts and known numeric statement amounts. "
            "No account numbers, addresses, credentials or graphs.",
            "casa_get_utilities_insights",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_utilities_insights(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[UtilitiesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "utilities_insights",
            lambda api, home: api.utilities_insights(home),
            lambda value: project_utilities(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Property tax refresh status and minimal report dates/years/total due. "
            "No owner identity, links or payment details.",
            "casa_get_property_taxes",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_property_taxes(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PropertyTaxesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "property_taxes",
            lambda api, home: api.property_taxes(home),
            lambda value: project_property_taxes(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Pending/approved/purchased metadata, prices and dates, preserving lane. "
            "Return notes require include_notes=true. "
            "No cards, invoice URLs or approval/payment changes.",
            "casa_list_purchases",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_purchases(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_notes: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PurchasesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "purchases",
            lambda api, home: api.purchases(home),
            lambda value: project_purchases(
                value, include_notes=include_notes, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Onboarding available slot start_time, timezone and duration. Read only, no booking.",
            "casa_list_onboarding_availability",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_onboarding_availability(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[OnboardingAvailabilityData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "onboarding_availability",
            lambda api, home: api.onboarding_availability(home),
            lambda value: project_onboarding_availability(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Onboarding calendar actual start_at/end_at timestamps. "
            "Bodyless 304 reported as not_modified, not empty calendar.",
            "casa_list_onboarding_calendar",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_onboarding_calendar(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[OnboardingCalendarData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "onboarding_details_typed",
            lambda api, home: api.onboarding_details_typed(home),
            lambda value: project_onboarding_calendar(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Room image candidate IDs/current flags and member-image presence only. "
            "No URLs or downloads.",
            "casa_get_room_photo_metadata",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_room_photo_metadata(
        room_id: EntityId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[RoomImagesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "room_image_options",
            lambda api, home: api.room_image_options(home, room_id),
            lambda value: project_room_images(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Photo IDs and home-hero flags only. No URLs, cache keys or downloads.",
            "casa_list_photo_metadata",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_photo_metadata(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PhotosData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "matterport_images",
            lambda api, home: api.matterport_images(home),
            lambda value: project_photos(value, offset=offset, limit=limit),
        )
