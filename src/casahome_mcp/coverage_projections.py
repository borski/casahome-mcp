"""Concrete allowlists for additional reads. Unknown payloads never cross MCP."""

import re
from collections.abc import Callable, Sequence
from typing import TypeVar
from unicodedata import category

from casahome.models.ai import CasaAIBootstrapResponse, CasaAIMessage, CasaAIMessagesResponse
from casahome.models.assets import (
    HomeVehicle,
    UtilitiesInsightsResponse,
    UtilityInsightsService,
    VehiclesResponse,
)
from casahome.models.documents import (
    DocumentsResponse,
    DocumentTypesResponse,
    HomeDocument,
    WorkDocumentSourceResponse,
)
from casahome.models.images import MatterportImage, RoomImageOptionsResponse
from casahome.models.maintenance import (
    AutopilotCategory,
    AutopilotIneligiblePlan,
    AutopilotPlan,
    CompletedRequestsResponse,
    InventoryServiceHistoryResponse,
)
from casahome.models.paint import (
    PaintBrand,
    PaintBrandsResponse,
    PaintCollection,
    PaintCollectionsResponse,
    PaintColor,
    PaintColorsResponse,
    PaintSearchResponse,
)
from casahome.models.preferences import (
    NotificationGroup,
    NotificationSettingsResponse,
    OnboardingAvailabilityResponse,
    OnboardingDetailsResponse,
    SchedulePreferencesResponse,
)
from casahome.models.purchases import (
    ApprovedPurchase,
    PurchaseApproval,
    PurchasedItem,
    PurchasesResponse,
)
from casahome.models.read_todos import SuggestedTodosResponse, TodoDetailsResponse, TodoReadDetail
from casahome.models.taxes import PropertyTaxesResponse

from .coverage_outputs import (
    AIBootstrapData,
    AIHistoryData,
    AIMessagePartSummary,
    AIMessageSummary,
    AutopilotPlansData,
    CitationSummary,
    CompletedCard,
    CompletedRequestsData,
    DocumentsData,
    DocumentSourceSummary,
    DocumentSummary,
    DocumentTypesData,
    DocumentTypeSummary,
    HistoryItem,
    HistoryPlan,
    NotificationChannelSummary,
    NotificationGroupSummary,
    NotificationsData,
    NotificationTypeSummary,
    OnboardingAvailabilityData,
    OnboardingCalendarData,
    OnboardingEventSummary,
    OnboardingSlotSummary,
    PaintCatalogData,
    PaintCatalogSummary,
    PaintColorsData,
    PaintColorSummary,
    PhotosData,
    PhotoSummary,
    PlanAssociation,
    PlanPricingPolicy,
    PlanSummary,
    PropertyTaxesData,
    PurchasesData,
    PurchaseSummary,
    RoomImagesData,
    RoomImageSummary,
    SchedulePreferencesData,
    SchedulingDaySummary,
    SchedulingWindowSummary,
    ServiceHistoryData,
    SuggestedTodosData,
    TaxReportSummary,
    TodoDetailsData,
    TodoReadSummary,
    UpstreamPagination,
    UtilitiesData,
    UtilityStatementSummary,
    UtilitySummary,
    VehiclesData,
    VehicleSummary,
    WorkDocumentSourceData,
)
from .outputs import OutputModel, Page
from .projections import _URL_VALUE, _clip, _warn, page, validate_pagination

S = TypeVar("S")
T = TypeVar("T", bound=OutputModel)
OPAQUE_CURSOR_PATTERN = r"^[A-Za-z0-9_+/=.-]{1,2048}$"


def text(value: str | None, warnings: list[str], maximum: int = 256) -> str | None:
    """Check the entire string before clipping, including invisible controls."""
    if value is None:
        return None
    if _URL_VALUE.search(value):
        _warn(warnings, "URL_TEXT_OMITTED")
        return None
    # Narrative newlines/tabs are data. Other controls and invisible format chars aren't.
    if any(category(c) in {"Cc", "Cf"} and c not in "\n\t" for c in value):
        _warn(warnings, "CONTROL_TEXT_OMITTED")
        return None
    return _clip(value, maximum, warnings)


def identity(value: str | None, warnings: list[str]) -> str | None:
    if value is not None and (
        not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value)
        or any(category(c) in {"Cc", "Cf"} for c in value)
    ):
        _warn(warnings, "UNSAFE_ID_OMITTED")
        return None
    return value


def cursor(value: str | None, warnings: list[str]) -> str | None:
    # A cursor is neither a URL nor an auth credential. Don't apply domain/JWT
    # heuristics that would reject valid opaque pagination data. Never clip it.
    if value is not None and (
        value == "null"
        or value.lower().startswith(("//", "../", "www."))
        or re.fullmatch(OPAQUE_CURSOR_PATTERN, value) is None
    ):
        _warn(warnings, "UNSAFE_CURSOR_OMITTED")
        return None
    return value


def nested(items: Sequence[S], warnings: list[str], maximum: int = 20) -> Sequence[S]:
    if len(items) > maximum:
        _warn(warnings, "NESTED_COLLECTION_TRUNCATED")
    return items[:maximum]


def local_page(
    items: Sequence[S], project: Callable[[S], T], warnings: list[str], offset: int, limit: int
) -> Page[T]:
    result = page(items, project=project, offset=offset, limit=limit)
    if result.has_more_in_response:
        _warn(warnings, "LOCAL_PAGE_TRUNCATED")
    return result


def _todo(model: TodoReadDetail, include_brief: bool, warnings: list[str]) -> TodoReadSummary:
    return TodoReadSummary(
        id=identity(model.id, warnings),
        title=text(model.title, warnings),
        status=text(str(model.status), warnings),
        creator_role=text(str(model.creator_role), warnings),
        created_at=model.created_at,
        updated_at=model.updated_at,
        is_suggested=model.is_suggested,
        flagged_for_support=model.flagged_for_support,
        attachment_count=len(model.attachments),
        prepared_brief=text(model.prepared_brief, warnings, 2000) if include_brief else None,
    )


def project_suggested_todos(
    model: SuggestedTodosResponse, *, include_brief: bool = False, offset: int = 0, limit: int = 25
) -> tuple[SuggestedTodosData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return SuggestedTodosData(
        page=local_page(
            model.suggested_todos,
            lambda item: _todo(item, include_brief, warnings),
            warnings,
            offset,
            limit,
        )
    ), warnings


def project_todo_details(
    model: TodoDetailsResponse, *, include_brief: bool = False
) -> tuple[TodoDetailsData, list[str]]:
    warnings: list[str] = []
    return TodoDetailsData(todo=_todo(model.todo, include_brief, warnings)), warnings


def project_completed_requests(
    model: CompletedRequestsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[CompletedRequestsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "UPSTREAM_QUERY_BEHAVIOR_UNVERIFIED"]
    p = model.pagination
    return CompletedRequestsData(
        kind=text(model.kind, warnings),
        upstream_pagination=UpstreamPagination(
            page=p.page, page_size=p.page_size, total_count=p.total_count, total_pages=p.total_pages
        ),
        page=local_page(
            model.items,
            lambda item: CompletedCard(
                id=identity(item.id, warnings),
                type=text(str(item.type), warnings),
                title=text(item.title, warnings),
                updated_at=item.updated_at,
                has_unread_messages=item.has_unread_messages,
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def _plan(
    category_model: AutopilotCategory,
    model: AutopilotPlan | AutopilotIneligiblePlan,
    warnings: list[str],
) -> PlanSummary:
    eligible = isinstance(model, AutopilotPlan)
    associations: list[PlanAssociation] = []
    if isinstance(model, AutopilotPlan):
        if (home := model.home_association) is not None:
            associations.append(
                PlanAssociation(
                    kind="home",
                    id=identity(home.id, warnings),
                    target_id=None,
                    name=None,
                    duration_minutes=home.duration_minutes,
                    enabled=home.enabled,
                    price_usd_cents=home.price_usd_cents,
                )
            )
        for room in nested(model.room_associations, warnings):
            associations.append(
                PlanAssociation(
                    kind="room",
                    id=identity(room.id, warnings),
                    target_id=identity(room.room_id, warnings),
                    name=text(room.room_name, warnings),
                    duration_minutes=room.duration_minutes,
                    enabled=room.enabled,
                    price_usd_cents=room.price_usd_cents,
                )
            )
        for entity in nested(model.entity_associations, warnings):
            associations.append(
                PlanAssociation(
                    kind="entity",
                    id=identity(entity.id, warnings),
                    target_id=identity(entity.entity_id, warnings),
                    name=text(entity.entity_display_name, warnings),
                    duration_minutes=entity.duration_minutes,
                    enabled=entity.enabled,
                    price_usd_cents=entity.price_usd_cents,
                )
            )
    return PlanSummary(
        category_id=identity(category_model.category_id, warnings),
        category_title=text(category_model.category_title, warnings),
        plan_id=identity(model.plan_id, warnings) if isinstance(model, AutopilotPlan) else None,
        plan_template_id=identity(model.plan_template_id, warnings),
        eligible=eligible,
        title=text(model.title, warnings),
        subtitle=text(model.subtitle, warnings),
        description=text(model.description, warnings, 2000),
        type=text(model.type, warnings),
        fulfillment_policy=text(model.fulfillment_policy, warnings),
        enabled=model.enabled if isinstance(model, AutopilotPlan) else None,
        applies_to=text(model.applies_to, warnings) if isinstance(model, AutopilotPlan) else None,
        selected_cadence=text(model.selected_cadence, warnings)
        if isinstance(model, AutopilotPlan)
        else None,
        default_cadence=text(model.default_cadence, warnings)
        if isinstance(model, AutopilotPlan)
        else None,
        cadence_options=[text(value, warnings) for value in nested(model.cadence_options, warnings)]
        if isinstance(model, AutopilotPlan)
        else [],
        savings_percentage=model.savings_percentage if isinstance(model, AutopilotPlan) else None,
        next_calendar_event_start_at=model.next_calendar_event_start_at
        if isinstance(model, AutopilotPlan)
        else None,
        pricing_policies=[
            PlanPricingPolicy(
                title=text(item.title, warnings), description=text(item.description, warnings, 2000)
            )
            for item in nested(model.pricing_policies, warnings)
        ]
        if isinstance(model, AutopilotPlan)
        else [],
        associations=list(nested(associations, warnings)),
    )


def project_autopilot_plans(
    model: list[AutopilotCategory], *, offset: int = 0, limit: int = 25
) -> tuple[AutopilotPlansData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    rows: list[tuple[AutopilotCategory, AutopilotPlan | AutopilotIneligiblePlan]] = []
    for cat in model:
        rows.extend((cat, plan) for plan in cat.plans)
        rows.extend((cat, plan) for plan in cat.ineligible_plans)
    return AutopilotPlansData(
        page=local_page(rows, lambda row: _plan(row[0], row[1], warnings), warnings, offset, limit)
    ), warnings


def project_service_history(
    model: InventoryServiceHistoryResponse, *, offset: int = 0, limit: int = 25
) -> tuple[ServiceHistoryData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return ServiceHistoryData(
        plans=local_page(
            model.autopilot_plans,
            lambda item: HistoryPlan(
                id=identity(item.id, warnings),
                title=text(item.title, warnings),
                enabled=item.enabled,
                selected_cadence=text(item.selected_cadence, warnings),
                next_service_at=item.next_service_at,
            ),
            warnings,
            offset,
            limit,
        ),
        history=local_page(
            model.history_items,
            lambda item: HistoryItem(
                task_id=identity(item.task_id, warnings),
                task_type=text(item.task_type, warnings),
                task_title=text(item.task_title, warnings),
                serviced_at=item.serviced_at,
                autopilot_plan_id=identity(item.autopilot_plan_id, warnings),
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def _document(model: HomeDocument, warnings: list[str]) -> DocumentSummary:
    return DocumentSummary(
        id=identity(model.id, warnings),
        name=text(model.name, warnings),
        document_type=text(model.document_type, warnings),
        document_date=text(model.document_date, warnings),
        mimetype=text(model.mimetype, warnings),
        size_bytes=model.size_bytes,
        created_at=model.created_at,
        updated_at=model.updated_at,
        organization_status=text(model.organization.status, warnings)
        if model.organization
        else None,
        extraction_status=text(model.extraction.status, warnings) if model.extraction else None,
    )


def project_documents(
    model: DocumentsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[DocumentsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "UPSTREAM_QUERY_BEHAVIOR_UNVERIFIED"]
    return DocumentsData(
        page=local_page(
            model.documents, lambda item: _document(item, warnings), warnings, offset, limit
        ),
        next_cursor=cursor(model.next_cursor, warnings),
    ), warnings


def project_document_types(
    model: DocumentTypesResponse, *, offset: int = 0, limit: int = 25
) -> tuple[DocumentTypesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return DocumentTypesData(
        page=local_page(
            model.types,
            lambda item: DocumentTypeSummary(
                key=identity(item.key, warnings),
                label=text(item.label, warnings),
                description=text(item.description, warnings, 2000),
            ),
            warnings,
            offset,
            limit,
        ),
        max_file_size_bytes=model.max_file_size_bytes,
        max_files_per_upload=model.max_files_per_upload,
        max_organization_size_bytes=model.max_organization_size_bytes,
        allowed_mimetypes=[
            text(item, warnings) for item in nested(model.allowed_mimetypes, warnings, 100)
        ],
    ), warnings


def project_work_document_source(
    model: WorkDocumentSourceResponse,
    *,
    include_excerpts: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[WorkDocumentSourceData, list[str]]:
    validate_pagination(offset=offset, limit=limit)
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    source = model.source
    if source is None:
        return WorkDocumentSourceData(source=None), warnings
    return WorkDocumentSourceData(
        source=DocumentSourceSummary(
            document_id=identity(source.document_id, warnings),
            name=text(source.name, warnings),
            available=source.available,
            document_date=text(source.document_date, warnings),
            citations=local_page(
                source.citations,
                lambda item: CitationSummary(
                    page_index=item.page_index,
                    page_label=text(item.page_label, warnings),
                    excerpt=text(item.excerpt, warnings, 2000) if include_excerpts else None,
                ),
                warnings,
                offset,
                limit,
            ),
        )
    ), warnings


def _catalog(model: PaintBrand | PaintCollection, warnings: list[str]) -> PaintCatalogSummary:
    return PaintCatalogSummary(
        id=model.id if type(model.id) is int else identity(str(model.id), warnings),
        name=text(model.name, warnings),
        color_count=model.color_count,
    )


def _color(model: PaintColor, warnings: list[str]) -> PaintColorSummary:
    return PaintColorSummary(
        id=model.id if type(model.id) is int else identity(str(model.id), warnings),
        color_name=text(model.color_name, warnings),
        brand_name=text(model.brand_name, warnings),
        collection_name=text(model.collection_name, warnings),
        color_hex=text(model.color_hex, warnings),
    )


def project_paint_brands(
    model: PaintBrandsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[PaintCatalogData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PaintCatalogData(
        page=local_page(
            model.brands, lambda item: _catalog(item, warnings), warnings, offset, limit
        )
    ), warnings


def project_paint_collections(
    model: PaintCollectionsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[PaintCatalogData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PaintCatalogData(
        page=local_page(
            model.collections, lambda item: _catalog(item, warnings), warnings, offset, limit
        )
    ), warnings


def project_paint_colors(
    model: PaintColorsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[PaintColorsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PaintColorsData(
        page=local_page(model.colors, lambda item: _color(item, warnings), warnings, offset, limit)
    ), warnings


def project_paint_search(
    model: PaintSearchResponse, *, offset: int = 0, limit: int = 25
) -> tuple[PaintColorsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PaintColorsData(
        page=local_page(model.results, lambda item: _color(item, warnings), warnings, offset, limit)
    ), warnings


def project_schedule_preferences(
    model: SchedulePreferencesResponse, *, offset: int = 0, limit: int = 25
) -> tuple[SchedulePreferencesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return SchedulePreferencesData(
        days=local_page(
            model.days_of_week,
            lambda item: SchedulingDaySummary(
                day_of_week=item.day_of_week, label=text(item.label, warnings), enabled=item.enabled
            ),
            warnings,
            offset,
            limit,
        ),
        windows=local_page(
            model.times_of_day,
            lambda item: SchedulingWindowSummary(
                id=identity(item.id, warnings),
                title=text(item.window_title, warnings),
                time_range=text(item.window_time_range, warnings),
                enabled=item.enabled,
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def _notification(model: NotificationGroup, warnings: list[str]) -> NotificationGroupSummary:
    return NotificationGroupSummary(
        key=identity(model.key, warnings),
        display_name=text(model.display_name, warnings),
        sort_order=model.sort_order,
        types=[
            NotificationTypeSummary(
                key=identity(item.key, warnings),
                display_name=text(item.display_name, warnings),
                sort_order=item.sort_order,
                channels=[
                    NotificationChannelSummary(
                        channel=text(channel.channel, warnings),
                        enabled=channel.enabled,
                        default_enabled=channel.default_enabled,
                        required=channel.required,
                    )
                    for channel in nested(item.channels, warnings)
                ],
            )
            for item in nested(model.types, warnings)
        ],
    )


def project_notifications(
    model: NotificationSettingsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[NotificationsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return NotificationsData(
        page=local_page(
            model.groups, lambda item: _notification(item, warnings), warnings, offset, limit
        )
    ), warnings


def _string_field(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _ai_message(
    model: CasaAIMessage, include_messages: bool, warnings: list[str]
) -> AIMessageSummary:
    parts: list[AIMessagePartSummary] | None = None
    if include_messages:
        parts = []
        for part in nested(model.parts, warnings):
            if part.type == "text":
                parts.append(
                    AIMessagePartSummary(type="text", text=text(part.text, warnings, 2000))
                )
            elif part.type == "data-todo":
                data = (part.model_extra or {}).get("data")
                if isinstance(data, dict):
                    parts.append(
                        AIMessagePartSummary(
                            type="data-todo",
                            todo_id=identity(_string_field(data, "todo_id"), warnings),
                            title=text(_string_field(data, "title"), warnings),
                            status=text(_string_field(data, "status"), warnings),
                        )
                    )
                else:
                    _warn(warnings, "OPAQUE_MESSAGE_PARTS_OMITTED")
            else:
                _warn(warnings, "OPAQUE_MESSAGE_PARTS_OMITTED")
    elif model.parts:
        _warn(warnings, "OPAQUE_MESSAGE_PARTS_OMITTED")
    return AIMessageSummary(
        id=identity(model.id, warnings),
        sender_role=text(model.sender_role, warnings),
        created_at=model.created_at,
        content=text(model.content, warnings, 2000) if include_messages else None,
        parts=parts,
    )


def project_ai_history(
    model: CasaAIMessagesResponse,
    *,
    include_messages: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[AIHistoryData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "UPSTREAM_QUERY_BEHAVIOR_UNVERIFIED"]
    return AIHistoryData(
        page=local_page(
            model.items,
            lambda item: _ai_message(item, include_messages, warnings),
            warnings,
            offset,
            limit,
        ),
        next_cursor=cursor(model.next_cursor, warnings),
    ), warnings


def project_ai_bootstrap(
    model: CasaAIBootstrapResponse,
    *,
    include_messages: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[AIBootstrapData, list[str]]:
    history, warnings = project_ai_history(
        model.messages, include_messages=include_messages, offset=offset, limit=limit
    )
    return AIBootstrapData(
        conversation_id=identity(model.conversation.id, warnings) if model.conversation else None,
        messages=history,
        active_response_present=model.active_response is not None,
        starter_suggestions=[
            text(item.prompt, warnings, 2000)
            for item in nested(model.starter_suggestions, warnings)
        ]
        if include_messages
        else None,
    ), warnings


def _vehicle(model: HomeVehicle, warnings: list[str]) -> VehicleSummary:
    return VehicleSummary(
        id=identity(model.id, warnings),
        display_name=text(model.display_name, warnings),
        status=text(model.status, warnings),
        make=text(model.make, warnings),
        model=text(model.model, warnings),
        year=model.year,
        powertrain_type=text(model.powertrain.type, warnings) if model.powertrain else None,
        powertrain_name=text(model.powertrain.display_name, warnings) if model.powertrain else None,
    )


def project_vehicles(
    model: VehiclesResponse, *, offset: int = 0, limit: int = 25
) -> tuple[VehiclesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return VehiclesData(
        page=local_page(
            model.vehicles, lambda item: _vehicle(item, warnings), warnings, offset, limit
        )
    ), warnings


def _utility(model: UtilityInsightsService, warnings: list[str]) -> UtilitySummary:
    return UtilitySummary(
        id=identity(model.id, warnings),
        service_type=text(model.service_type, warnings),
        usage_unit=text(model.usage_unit, warnings),
        account_count=len(model.accounts),
        statement_count=len(model.statements),
        graph_count=len(model.interval_graphs),
        statements=[
            UtilityStatementSummary(
                ends_at=item.ends_at,
                total_amount_usd_due=item.total_amount_usd_due,
                service_usage_amount=item.service_usage_amount,
                service_amount_usd=item.service_amount_usd,
            )
            for item in nested(model.statements, warnings)
        ],
    )


def project_utilities(
    model: UtilitiesInsightsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[UtilitiesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return UtilitiesData(
        page=local_page(
            model.services, lambda item: _utility(item, warnings), warnings, offset, limit
        )
    ), warnings


def project_property_taxes(
    model: PropertyTaxesResponse, *, offset: int = 0, limit: int = 25
) -> tuple[PropertyTaxesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PropertyTaxesData(
        next_tax_bill_release_at=model.next_tax_bill_release_at,
        refresh_status=text(model.refresh.status, warnings) if model.refresh else None,
        next_fetch_at=model.refresh.next_fetch_at if model.refresh else None,
        page=local_page(
            model.reports,
            lambda item: TaxReportSummary(
                id=identity(item.id, warnings),
                issued_at=item.issued_at,
                tax_year_start=item.tax_year_start,
                tax_year_end=item.tax_year_end,
                total_tax_due=item.total_tax_due,
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def _purchase(
    model: PurchaseApproval | PurchasedItem, include_notes: bool, warnings: list[str]
) -> PurchaseSummary:
    approved = isinstance(model, ApprovedPurchase)
    purchased = isinstance(model, PurchasedItem)
    return PurchaseSummary(
        lane="purchased" if purchased else "approved" if approved else "pending",
        id=identity(model.id, warnings),
        title=text(model.title, warnings),
        vendor_name=text(model.vendor.name, warnings) if model.vendor else None,
        unit_price_usd_cents=model.unit_price_usd_cents,
        quantity=model.quantity,
        updated_at=model.updated_at,
        purchased_at=model.purchased_at if isinstance(model, PurchasedItem) else None,
        approved_at=model.approved_at if isinstance(model, ApprovedPurchase) else None,
        is_voided=model.is_voided if isinstance(model, ApprovedPurchase) else None,
        return_by_date=model.return_by_date if isinstance(model, PurchasedItem) else None,
        return_policy_notes=text(model.return_policy_notes, warnings, 2000)
        if include_notes
        else None,
    )


def project_purchases(
    model: PurchasesResponse, *, include_notes: bool = False, offset: int = 0, limit: int = 25
) -> tuple[PurchasesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    items: list[PurchaseApproval | PurchasedItem] = [
        *model.pending_purchase_approvals,
        *model.approved_purchases,
        *model.purchased_items,
    ]
    return PurchasesData(
        context_title=text(model.context_title, warnings),
        next_package_pickup_by=model.next_package_pickup_by,
        non_purchase_invoice_count=len(model.non_purchase_invoices),
        page=local_page(
            items, lambda item: _purchase(item, include_notes, warnings), warnings, offset, limit
        ),
    ), warnings


def project_onboarding_availability(
    model: OnboardingAvailabilityResponse, *, offset: int = 0, limit: int = 25
) -> tuple[OnboardingAvailabilityData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    return OnboardingAvailabilityData(
        message=text(model.message, warnings),
        timezone=text(model.timezone, warnings),
        number_of_required_vendors=model.number_of_required_vendors,
        estimated_visit_duration_seconds=model.estimated_visit_duration_seconds,
        page=local_page(
            model.available_slots,
            lambda item: OnboardingSlotSummary(
                start_time=item.start_time, vendor_count=len(item.vendor_ids)
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_onboarding_calendar(
    model: OnboardingDetailsResponse | None, *, offset: int = 0, limit: int = 25
) -> tuple[OnboardingCalendarData, list[str]]:
    validate_pagination(offset=offset, limit=limit)
    if model is None:
        return OnboardingCalendarData(not_modified=True, page=None), ["UPSTREAM_NOT_MODIFIED"]
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    return OnboardingCalendarData(
        not_modified=False,
        page=local_page(
            model.calendar_events,
            lambda item: OnboardingEventSummary(
                id=identity(item.id, warnings), start_at=item.start_at, end_at=item.end_at
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_room_images(
    model: RoomImageOptionsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[RoomImagesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return RoomImagesData(
        member_image_present=model.member_image is not None,
        page=local_page(
            model.matterport_images,
            lambda item: RoomImageSummary(
                id=identity(item.id, warnings), is_current=item.is_current
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_photos(
    model: list[MatterportImage], *, offset: int = 0, limit: int = 25
) -> tuple[PhotosData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PhotosData(
        page=local_page(
            model,
            lambda item: PhotoSummary(
                id=identity(item.id, warnings), is_home_hero_image=item.is_home_hero_image
            ),
            warnings,
            offset,
            limit,
        )
    ), warnings
