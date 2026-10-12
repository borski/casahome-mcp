"""Explicit detail GET tools. The shared read policy owns runtime gating."""

from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from .coverage_tools import OptionalPathId
from .detail_outputs import (
    AvailabilityDetailsData,
    BookableTasksData,
    DocumentDetailsData,
    DocumentSuggestionsData,
    HelpCenterData,
    HomeFeedData,
    InventoryEnumsData,
    MembershipInfoData,
    MembershipSavingsData,
    PaintMatchesData,
    ReferralCodeData,
    ReleaseNotesData,
    ScopedPurchasesData,
    StructureSuggestionsData,
    TaskDetailsData,
    VendorVisitDetailsData,
    VisitAutopilotPlanData,
    VisitCallsData,
    VisitConversationData,
)
from .detail_projections import (
    project_availability_request_details,
    project_bookable_handyman_tasks,
    project_document_details,
    project_document_structure_suggestions,
    project_document_suggestions,
    project_help_center_bundle,
    project_home_feed,
    project_inventory_enums,
    project_inventory_paint_matches,
    project_membership_info,
    project_membership_savings,
    project_referral_code,
    project_release_notes_diff,
    project_scoped_purchases,
    project_task_details,
    project_vendor_visit_autopilot_plan,
    project_vendor_visit_calls,
    project_vendor_visit_conversation,
    project_vendor_visit_details,
)
from .errors import failure
from .outputs import ToolResponse
from .runtime import AppContext
from .tools import EntityId, HomeId, Limit, Offset, RequestId, describe, read

PathId = Annotated[
    RequestId, Field(description="Caller-supplied Casa identifier, one ASCII path segment.")
]
EnumTypeKey = Annotated[
    RequestId,
    Field(description="Property enum_type string key, e.g. light_fixture_type. Not a UUID."),
]


def register_detail_tools(server: MCPServer) -> None:
    remote = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
    )

    @server.tool(
        description=describe(
            "Bookable handyman item count and additional availability minutes only. "
            "Opaque tagged items omitted, never decoded. Optional visit-query behavior unverified. "
            "No booking.",
            "casa_list_bookable_handyman_tasks",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_bookable_handyman_tasks(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_current_vendor_visit_id: OptionalPathId = None,
    ) -> ToolResponse[BookableTasksData]:
        # The query is statically recovered only. The default remains the
        # parameter-free SDK call whose envelope has evidence.
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "bookable_handyman_tasks",
            lambda api, home: api.bookable_handyman_tasks(
                home, include_current_vendor_visit_id=include_current_vendor_visit_id
            ),
            lambda value: project_bookable_handyman_tasks(
                value, query_requested=include_current_vendor_visit_id is not None
            ),
        )

    @server.tool(
        description=describe(
            "Membership name, member_since and bounded benefit descriptions. "
            "Opaque benefit IDs omitted. "
            "No billing amounts, billing interval, next bill, payment or owner details.",
            "casa_get_membership_info",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_membership_info(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[MembershipInfoData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "membership_info",
            lambda api, home: api.membership_info(home),
            lambda value: project_membership_info(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Membership savings in explicit SDK seconds/cents, categories and breakdown. "
            "No inferred currency/reporting period, billing or owner details.",
            "casa_get_membership_savings",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_membership_savings(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[MembershipSavingsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "membership_savings",
            lambda api, home: api.membership_savings(home),
            lambda value: project_membership_savings(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Inventory enum options for a property's enum_type key, such as "
            "light_fixture_type or home_type. Not a UUID, entity-type or make ID. "
            "Catalog GET requires a configured home for policy only. No icon URLs.",
            "casa_list_inventory_enums",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_inventory_enums(
        enum_type: EnumTypeKey,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[InventoryEnumsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "inventory_enums",
            lambda api, home: api.inventory_enums(enum_type),
            lambda value: project_inventory_enums(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Release notes newer than the app build the SDK reports (698): title, version, "
            "date, build range and section titles. Prelude and section text require "
            "include_content=true. No image URLs or highest-known-build mutation. "
            "Configured home is policy only.",
            "casa_get_release_notes_diff",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_release_notes_diff(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_content: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[ReleaseNotesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "release_notes_diff",
            lambda api, home: api.release_notes_diff(),
            lambda value: project_release_notes_diff(
                value, include_content=include_content, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Availability-request status, constraints, timezone and raw slot timestamps. "
            "No selection, submission or scheduling.",
            "casa_get_availability_request_details",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_availability_request_details(
        availability_request_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[AvailabilityDetailsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "availability_request_details",
            lambda api, home: api.availability_request_details(home, availability_request_id),
            lambda value: project_availability_request_details(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "One document's metadata and organization/extraction status. No filenames, owner, URL, "
            "download, analysis or organization actions. Deletion prepare reads again separately.",
            "casa_get_document_details",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_document_details(
        document_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> ToolResponse[DocumentDetailsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "document_details",
            lambda api, home: api.document_details(home, document_id),
            project_document_details,
        )

    @server.tool(
        description=describe(
            "Existing document suggestions, state and citation page labels. "
            "Citation excerpts require "
            "include_excerpts=true. No analysis, work creation, acceptance or dismissal.",
            "casa_list_document_suggestions",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_document_suggestions(
        document_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        view: Literal["all"] | None = "all",
        include_excerpts: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[DocumentSuggestionsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "document_suggestions",
            lambda api, home: api.document_suggestions(home, document_id, view=view),
            lambda value: project_document_suggestions(
                value, include_excerpts=include_excerpts, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Existing structure suggestions, bounded labels/values, state "
            "and citation page labels. "
            "Excerpts require include_excerpts=true. current_values_complete is advisory only. "
            "Action preparation refetches and checks eligibility. No action on this read.",
            "casa_list_document_structure_suggestions",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_document_structure_suggestions(
        document_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_excerpts: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[StructureSuggestionsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "document_structure_suggestions",
            lambda api, home: api.document_structure_suggestions(home, document_id),
            lambda value: project_document_structure_suggestions(
                value, include_excerpts=include_excerpts, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Paint matches by canonical entity UUID. "
            "Catalog names/hex/closeness and manual flag only. "
            "No match application.",
            "casa_get_inventory_paint_matches",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_inventory_paint_matches(
        entity_id: EntityId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[PaintMatchesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "inventory_paint_matches",
            lambda api, home: api.inventory_paint_matches(home, entity_id),
            lambda value: project_inventory_paint_matches(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Request purchase metadata preserving pending/approved/purchased lanes. "
            "Return notes opt-in "
            "via include_notes. No links, invoices, payment, approval or returns actions.",
            "casa_list_request_purchases",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_request_purchases(
        request_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_notes: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[ScopedPurchasesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "request_purchases",
            lambda api, home: api.request_purchases(home, request_id),
            lambda value: project_scoped_purchases(
                value, include_notes=include_notes, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Task metadata, description, flags and update metadata. Update message text requires "
            "include_messages=true. Attachments counted only. "
            "Read only. Scalar edit has a separately gated prepare. "
            "No schedule, delete or transfer.",
            "casa_get_task_details",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_task_details(
        task_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_messages: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[TaskDetailsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "task_details",
            lambda api, home: api.task_details(home, task_id),
            lambda value: project_task_details(
                value, include_messages=include_messages, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Visit/request/vendor/calendar and conversation-window metadata. "
            "Opaque task items and feedback omitted, invoices/purchases counted only. "
            "No message previews, URLs, locations or mutation.",
            "casa_get_vendor_visit_details",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_vendor_visit_details(
        visit_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> ToolResponse[VendorVisitDetailsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "vendor_visit_details",
            lambda api, home: api.vendor_visit_details(home, visit_id),
            project_vendor_visit_details,
        )

    @server.tool(
        description=describe(
            "One visit's grouped Autopilot plan/task/target metadata. Update message text opt-in "
            "via include_messages. No images, scheduling or plan changes.",
            "casa_get_vendor_visit_autopilot_plan",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_vendor_visit_autopilot_plan(
        visit_id: PathId,
        plan_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_messages: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[VisitAutopilotPlanData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "vendor_visit_autopilot_plan",
            lambda api, home: api.vendor_visit_autopilot_plan(home, visit_id, plan_id),
            lambda value: project_vendor_visit_autopilot_plan(
                value, include_messages=include_messages, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Visit call history metadata/times/duration/recorded flag and participant count only. "
            "No join URL, access grant, phone, user IDs, call control or recording downloads.",
            "casa_list_vendor_visit_calls",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_vendor_visit_calls(
        visit_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[VisitCallsData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "vendor_visit_calls",
            lambda api, home: api.vendor_visit_calls(home, visit_id),
            lambda value: project_vendor_visit_calls(value, offset=offset, limit=limit),
        )

    @server.tool(
        description=describe(
            "Visit conversation metadata and bounded participants/messages. "
            "Text only with explicit "
            "include_messages=true. Unknown parts, attachments, URLs and event cursors omitted. "
            "No send, mark-read, call or stream.",
            "casa_get_vendor_visit_conversation",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_vendor_visit_conversation(
        visit_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_messages: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[VisitConversationData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "vendor_visit_conversation",
            lambda api, home: api.vendor_visit_conversation(home, visit_id),
            lambda value: project_vendor_visit_conversation(
                value, include_messages=include_messages, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Visit purchase metadata preserving pending/approved/purchased lanes. "
            "Return notes opt-in "
            "via include_notes. No links, invoices, payments, approvals or returns actions.",
            "casa_list_vendor_visit_purchases",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_list_vendor_visit_purchases(
        visit_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        include_notes: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[ScopedPurchasesData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "vendor_visit_purchases",
            lambda api, home: api.vendor_visit_purchases(home, visit_id),
            lambda value: project_scoped_purchases(
                value, include_notes=include_notes, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Help topic or article metadata by caller-supplied app path ID. "
            "Only member_ios has been observed. Article body requires include_body=true "
            "and kind=articles. "
            "Configured home is policy only. No hero URLs, view tracking or feedback.",
            "casa_get_help_center_bundle",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_help_center_bundle(
        app_id: PathId,
        ctx: Context[AppContext],
        home_id: HomeId = None,
        kind: Literal["topics", "articles"] = "topics",
        include_body: bool = False,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[HelpCenterData]:
        if kind == "topics" and include_body:
            raise failure("INVALID_ARGUMENT")
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "help_center_bundle",
            lambda api, home: api.help_center_bundle(app_id),
            lambda value: project_help_center_bundle(
                value, kind=kind, include_body=include_body, offset=offset, limit=limit
            ),
        )

    @server.tool(
        description=describe(
            "Member referral code, string display labels and referred-home count. "
            "Referral URL, URL-shaped labels and referred-home details omitted. "
            "Configured home is policy only.",
            "casa_get_referral_code",
            items_unobserved=True,
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_referral_code(
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> ToolResponse[ReferralCodeData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "referral_code",
            lambda api, home: api.referral_code(),
            project_referral_code,
        )

    @server.tool(
        description=describe(
            "Home feed cards: id, template, name, allowlisted title/subtitle/feature/caption "
            "text, bare action tokens, onboarding progress counts and show window minutes. "
            "Colors, images, visual styling, URLs and other props omitted. "
            "Nested children counted only. No card actions.",
            "casa_get_home_feed",
        ),
        annotations=remote,
        structured_output=True,
    )
    async def casa_get_home_feed(
        ctx: Context[AppContext],
        home_id: HomeId = None,
        offset: Offset = 0,
        limit: Limit = 25,
    ) -> ToolResponse[HomeFeedData]:
        return await read(
            ctx.request_context.lifespan_context,
            home_id,
            "home_feed",
            lambda api, home: api.home_feed(home),
            lambda value: project_home_feed(value, offset=offset, limit=limit),
        )
