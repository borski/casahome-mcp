"""Static typed GET projections. Unknown unions are counted, never decoded."""

from collections.abc import Mapping, Sequence
from typing import Literal

from casahome.models.assets import ReleaseNotesResponse
from casahome.models.availability import MemberAvailabilityDetail
from casahome.models.catalogs import InventoryEnumsResponse
from casahome.models.documents import (
    DocumentCitation,
    DocumentDetailsResponse,
    DocumentStructureSuggestion,
    DocumentStructureSuggestionsResponse,
    DocumentSuggestionsResponse,
)
from casahome.models.feed import HomeFeedCard, HomeFeedResponse
from casahome.models.help_center import HelpCenterBundleResponse
from casahome.models.membership import MembershipDetails, MembershipSavings
from casahome.models.paint import InventoryPaintMatchesResponse
from casahome.models.purchases import PurchaseApproval, PurchasedItem, ScopedPurchasesResponse
from casahome.models.referral import ReferralCodeResponse
from casahome.models.tasks import (
    BookableHandymanTasksResponse,
    GroupedTaskDetails,
    GroupedTaskItem,
    TaskDetails,
    TaskDetailsVisit,
    TaskUpdate,
)
from casahome.models.visits import (
    VendorVisitDetails,
    VisitCallsResponse,
    VisitConversation,
    VisitConversationMessage,
    VisitConversationWindow,
)

from .coverage_outputs import CitationSummary
from .coverage_projections import _document, _purchase, identity, local_page, nested, text
from .detail_outputs import (
    AvailabilityConstraints,
    AvailabilityDetailsData,
    AvailabilitySlot,
    AvailabilitySummary,
    BenefitSummary,
    BookableTasksData,
    CallSummary,
    ConversationSummary,
    ConversationWindow,
    DocumentDetailsData,
    DocumentSuggestionsData,
    DocumentSuggestionSummary,
    FeedCardSummary,
    GroupedTaskSummary,
    HelpArticleSummary,
    HelpCenterData,
    HelpTopicSummary,
    HomeFeedData,
    InventoryEnumsData,
    InventoryEnumSummary,
    MembershipInfoData,
    MembershipSavingsData,
    PaintMatchesData,
    PaintMatchSummary,
    ParticipantSummary,
    ReferralCodeData,
    ReferralLabel,
    ReleaseNotesData,
    ReleaseNoteSummary,
    ReleaseSectionSummary,
    SavingsBreakdown,
    SavingsCategory,
    ScopedPurchasesData,
    StructureSuggestionsData,
    StructureSuggestionSummary,
    TaskDetailsData,
    TaskTargetSummary,
    TaskVisitSummary,
    UpdateSummary,
    VendorVisitDetailsData,
    VisitAutopilotPlanData,
    VisitCallsData,
    VisitConversationData,
    VisitEventSummary,
    VisitMessageSummary,
    VisitPlanSummary,
    VisitRequestSummary,
    VisitVendorSummary,
)
from .projections import _warn, validate_pagination
from .safe_values import exact_safe_text


def project_bookable_handyman_tasks(
    model: BookableHandymanTasksResponse,
    *,
    query_requested: bool = False,
) -> tuple[BookableTasksData, list[str]]:
    # The envelope is observed. The tagged union is not, even if a familiar
    # Swift case name appears in synthetic JSON. Never invent decoded rows.
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "OPAQUE_ITEMS_OMITTED"]
    if query_requested:
        _warn(warnings, "UPSTREAM_QUERY_BEHAVIOR_UNVERIFIED")
    return BookableTasksData(
        item_count=len(model.items),
        current_vendor_additional_availability_minutes=(
            model.current_vendor_additional_availability_minutes
        ),
        total_additional_availability_minutes=model.total_additional_availability_minutes,
    ), warnings


def project_membership_info(
    model: MembershipDetails, *, offset: int = 0, limit: int = 25
) -> tuple[MembershipInfoData, list[str]]:
    validate_pagination(offset=offset, limit=limit)
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    if model.benefits:
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
    return MembershipInfoData(
        name=text(model.name, warnings),
        member_since=model.member_since,
        benefits=local_page(
            model.benefits,
            lambda item: BenefitSummary(
                title=text(item.title, warnings),
                emoji=text(item.emoji, warnings),
                symbol=text(item.symbol, warnings),
                description=text(item.description, warnings, 2000),
            ),
            warnings,
            offset,
            limit,
        )
        if model.benefits is not None
        else None,
    ), warnings


def project_membership_savings(
    model: MembershipSavings, *, offset: int = 0, limit: int = 25
) -> tuple[MembershipSavingsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return MembershipSavingsData(
        calculated_at=text(model.calculated_at, warnings),
        total_time_saved_seconds=model.summary.total_time_saved_seconds,
        total_money_saved_cents=model.summary.total_money_saved_cents,
        page=local_page(
            model.categories,
            lambda item: SavingsCategory(
                type=text(item.type, warnings),
                label=text(item.label, warnings),
                color=text(item.color, warnings),
                preview=text(item.preview, warnings),
                is_visible=item.is_visible,
                time_saved_seconds=item.time_saved_seconds,
                money_saved_cents=item.money_saved_cents,
                breakdown=[
                    SavingsBreakdown(
                        title=text(row.title, warnings), value=text(row.value, warnings)
                    )
                    for row in nested(item.breakdown, warnings)
                ],
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_inventory_enums(
    model: InventoryEnumsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[InventoryEnumsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return InventoryEnumsData(
        page=local_page(
            model.enums,
            lambda item: InventoryEnumSummary(
                id=identity(item.id, warnings),
                type=text(item.type, warnings),
                name=text(item.name, warnings),
                symbol_name=text(item.symbol_name, warnings),
                category=text(item.category, warnings),
            ),
            warnings,
            offset,
            limit,
        )
    ), warnings


def project_release_notes_diff(
    model: ReleaseNotesResponse,
    *,
    include_content: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[ReleaseNotesData, list[str]]:
    """Note and section titles always. Prelude and section bodies only on opt-in.

    Hero image URLs are never projected, at note or section level.
    """
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    return ReleaseNotesData(
        page=local_page(
            model.data,
            lambda item: ReleaseNoteSummary(
                id=identity(item.id, warnings),
                title=text(item.title, warnings),
                version=text(item.version, warnings),
                date=item.date,
                min_build_number=item.min_build_number,
                max_build_number=item.max_build_number,
                prelude=text(item.prelude, warnings, 2000) if include_content else None,
                sections=[
                    ReleaseSectionSummary(
                        id=identity(row.id, warnings),
                        title=text(row.title, warnings),
                        content=text(row.content, warnings, 2000) if include_content else None,
                    )
                    for row in nested(item.sections, warnings)
                ],
            ),
            warnings,
            offset,
            limit,
        )
    ), warnings


def project_availability_request_details(
    model: MemberAvailabilityDetail, *, offset: int = 0, limit: int = 25
) -> tuple[AvailabilityDetailsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    item, constraints = model.availability_request, model.constraints
    return AvailabilityDetailsData(
        availability_request=AvailabilitySummary(
            id=identity(item.id, warnings),
            request_id=identity(item.request_id, warnings),
            status=text(item.status, warnings),
            slot_count=item.slot_count,
            first_submitted_at=item.first_submitted_at,
            last_submitted_at=item.last_submitted_at,
            created_at=item.created_at,
        ),
        home_timezone=text(model.home_timezone, warnings),
        constraints=AvailabilityConstraints(
            snap_minutes=constraints.snap_minutes,
            min_slot_minutes=constraints.min_slot_minutes,
            default_duration_minutes=constraints.default_duration_minutes,
            lead_time_minutes=constraints.lead_time_minutes,
        ),
        page=local_page(
            model.slots,
            lambda slot: AvailabilitySlot(
                id=identity(slot.id, warnings),
                start_time=slot.start_time,
                end_time=slot.end_time,
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_document_details(
    model: DocumentDetailsResponse,
) -> tuple[DocumentDetailsData, list[str]]:
    warnings: list[str] = []
    return DocumentDetailsData(document=_document(model.document, warnings)), warnings


def _citations(
    items: Sequence[DocumentCitation], include_excerpts: bool, warnings: list[str]
) -> list[CitationSummary]:
    return [
        CitationSummary(
            page_index=item.page_index,
            page_label=text(item.page_label, warnings),
            excerpt=text(item.excerpt, warnings, 2000) if include_excerpts else None,
        )
        for item in nested(items, warnings)
    ]


def project_document_suggestions(
    model: DocumentSuggestionsResponse,
    *,
    include_excerpts: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[DocumentSuggestionsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return DocumentSuggestionsData(
        analysis_status=text(model.analysis_status, warnings),
        limitations=[text(item, warnings, 2000) for item in nested(model.limitations, warnings)],
        page=local_page(
            model.suggestions,
            lambda item: DocumentSuggestionSummary(
                id=identity(item.id, warnings),
                todo_id=identity(item.todo_id, warnings),
                task_id=identity(item.task_id, warnings),
                request_id=identity(item.request_id, warnings),
                title=text(item.title, warnings),
                action=text(item.action, warnings),
                reason=text(item.reason, warnings, 2000),
                area=text(item.area, warnings),
                state=text(item.state, warnings),
                work_deleted=item.work_deleted,
                citations=_citations(item.citations, include_excerpts, warnings),
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_document_structure_suggestions(
    model: DocumentStructureSuggestionsResponse,
    *,
    include_excerpts: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[StructureSuggestionsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]

    def structure_item(item: DocumentStructureSuggestion) -> StructureSuggestionSummary:
        # A displayed clipped or unsafe value is never an exact preparation value.
        values = [text(value, warnings) for value in nested(item.current_values, warnings)]
        complete = len(values) == len(item.current_values) and all(
            projected == original and exact_safe_text(original, maximum=10_000)
            for projected, original in zip(values, item.current_values, strict=False)
        )
        if not complete:
            _warn(warnings, "INCOMPLETE_CURRENT_VALUES_NOT_SAFE_AS_GUARD")
        return StructureSuggestionSummary(
            id=identity(item.id, warnings),
            entity_id=identity(item.entity_id, warnings),
            definition_id=identity(item.definition_id, warnings),
            responded_at=item.responded_at,
            section=text(item.section, warnings),
            title=text(item.title, warnings),
            current_values=values,
            current_values_complete=complete,
            current_label=text(item.current_label, warnings),
            proposed_label=text(item.proposed_label, warnings),
            reason=text(item.reason, warnings, 2000),
            state=text(item.state, warnings),
            changed_since_analysis=item.changed_since_analysis,
            citations=_citations(item.citations, include_excerpts, warnings),
        )

    return StructureSuggestionsData(
        page=local_page(
            model.suggestions,
            structure_item,
            warnings,
            offset,
            limit,
        )
    ), warnings


def project_inventory_paint_matches(
    model: InventoryPaintMatchesResponse, *, offset: int = 0, limit: int = 25
) -> tuple[PaintMatchesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return PaintMatchesData(
        is_manually_added=model.is_manually_added,
        page=local_page(
            model.matches,
            lambda item: PaintMatchSummary(
                id=item.id,
                color_name=text(item.color_name, warnings),
                brand_name=text(item.brand_name, warnings),
                color_hex=text(item.color_hex, warnings),
                closeness_percentage=item.closeness_percentage,
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_scoped_purchases(
    model: ScopedPurchasesResponse, *, include_notes: bool = False, offset: int = 0, limit: int = 25
) -> tuple[ScopedPurchasesData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    items: list[PurchaseApproval | PurchasedItem] = [
        *model.pending_purchase_approvals,
        *model.approved_purchases,
        *model.purchased_items,
    ]
    return ScopedPurchasesData(
        context_title=text(model.context_title, warnings),
        next_package_pickup_by=model.next_package_pickup_by,
        page=local_page(
            items, lambda item: _purchase(item, include_notes, warnings), warnings, offset, limit
        ),
    ), warnings


def _task_visit(model: TaskDetailsVisit | None, warnings: list[str]) -> TaskVisitSummary | None:
    return (
        TaskVisitSummary(id=identity(model.id, warnings), start_time=model.start_time)
        if model
        else None
    )


def _update(model: TaskUpdate, include_messages: bool, warnings: list[str]) -> UpdateSummary:
    return UpdateSummary(
        id=identity(model.id, warnings),
        sender_name=text(model.sender_name, warnings),
        sent_at=model.sent_at,
        message=text(model.message, warnings, 2000) if include_messages else None,
        attachment_count=len(model.attachments or []),
    )


def project_task_details(
    model: TaskDetails, *, include_messages: bool = False, offset: int = 0, limit: int = 25
) -> tuple[TaskDetailsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    return TaskDetailsData(
        id=identity(model.id, warnings),
        title=text(model.title, warnings),
        description=text(model.description, warnings, 2000),
        emoji=text(model.emoji, warnings),
        status=text(model.status, warnings),
        visit=_task_visit(model.visit, warnings),
        attachment_count=len(model.attachments or []),
        can_schedule_handyman_vendor_visit=model.can_schedule_handyman_vendor_visit,
        can_chat_with_concierge=model.can_chat_with_concierge,
        can_edit=model.can_edit,
        can_delete=model.can_delete,
        page=local_page(
            model.updates,
            lambda item: _update(item, include_messages, warnings),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def _window(model: VisitConversationWindow, warnings: list[str]) -> ConversationWindow:
    return ConversationWindow(
        state=text(model.state, warnings),
        opens_at=model.opens_at,
        closes_at=model.closes_at,
        closed_reason=text(model.closed_reason, warnings),
    )


def project_vendor_visit_details(
    model: VendorVisitDetails,
) -> tuple[VendorVisitDetailsData, list[str]]:
    warnings = ["TIMESTAMP_UNITS_UNVERIFIED"]
    if model.task_items:
        _warn(warnings, "OPAQUE_ITEMS_OMITTED")
    if model.feedback is not None:
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
    request, event, conversation = model.request, model.calendar_event, model.conversation
    return VendorVisitDetailsData(
        id=identity(model.id, warnings),
        type=text(model.type, warnings),
        status=text(model.status, warnings),
        request=VisitRequestSummary(
            id=identity(request.id, warnings),
            type=text(request.type, warnings),
            status=text(request.status, warnings),
            title=text(request.title, warnings),
            emoji=text(request.emoji, warnings),
            has_unread_messages=request.has_unread_messages,
        ),
        calendar_event=VisitEventSummary(
            id=identity(event.id, warnings), start_time=event.start_time, end_time=event.end_time
        )
        if event
        else None,
        vendors=[
            VisitVendorSummary(
                id=identity(item.id, warnings),
                display_name=text(item.display_name, warnings),
                compact_display_name=text(item.compact_display_name, warnings),
                type=text(item.type, warnings),
                active_work_started_at=item.active_work_started_at,
            )
            for item in nested(model.vendors, warnings)
        ],
        task_item_count=len(model.task_items),
        invoice_count=len(model.invoices),
        purchase_count=len(model.purchases),
        can_add_remove_items=model.can_add_remove_items,
        can_cancel=model.can_cancel,
        conversation=ConversationSummary(
            thread_id=identity(conversation.thread_id, warnings),
            window=_window(conversation.window, warnings),
            calls_enabled=conversation.calls_enabled,
            unread_count=conversation.unread_count,
            counterparty_count=len(conversation.counterparties),
            live_call_present=conversation.live_call is not None,
        )
        if conversation
        else None,
    ), warnings


def _grouped_task(
    model: GroupedTaskItem, include_messages: bool, warnings: list[str]
) -> GroupedTaskSummary:
    target = model.target
    return GroupedTaskSummary(
        id=identity(model.id, warnings),
        status=text(model.status, warnings),
        target=TaskTargetSummary(
            id=identity(target.id, warnings),
            kind=text(target.kind, warnings),
            primary_label=text(target.primary_label, warnings),
            secondary_label=text(target.secondary_label, warnings),
            symbol_name=text(target.symbol_name, warnings),
        )
        if target
        else None,
        updates=[
            _update(item, include_messages, warnings) for item in nested(model.updates, warnings)
        ],
    )


def project_vendor_visit_autopilot_plan(
    model: GroupedTaskDetails, *, include_messages: bool = False, offset: int = 0, limit: int = 25
) -> tuple[VisitAutopilotPlanData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    plan = model.plan
    return VisitAutopilotPlanData(
        plan=VisitPlanSummary(
            id=identity(plan.id, warnings),
            title=text(plan.title, warnings),
            description=text(plan.description, warnings, 2000),
            emoji=text(plan.emoji, warnings),
        ),
        visit=_task_visit(model.visit, warnings),
        page=local_page(
            model.tasks,
            lambda item: _grouped_task(item, include_messages, warnings),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_vendor_visit_calls(
    model: VisitCallsResponse, *, offset: int = 0, limit: int = 25
) -> tuple[VisitCallsData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    return VisitCallsData(
        page=local_page(
            model.calls,
            lambda item: CallSummary(
                id=identity(item.id, warnings),
                vendor_visit_id=identity(item.vendor_visit_id, warnings),
                status=text(item.status, warnings),
                started_by_role=text(item.started_by_role, warnings),
                started_at=item.started_at,
                answered_at=item.answered_at,
                ended_at=item.ended_at,
                duration_seconds=item.duration_seconds,
                recorded=item.recorded,
                participant_count=len(item.participants),
            ),
            warnings,
            offset,
            limit,
        )
    ), warnings


def _message(
    model: VisitConversationMessage, include_messages: bool, warnings: list[str]
) -> VisitMessageSummary:
    if model.parts:
        _warn(warnings, "OPAQUE_PARTS_OMITTED")
    return VisitMessageSummary(
        id=identity(model.id, warnings),
        thread_id=identity(model.thread_id, warnings),
        created_at=model.created_at,
        sender_role=text(model.sender_role, warnings),
        sender_display_name=text(model.sender_display_name, warnings),
        is_mine=model.is_mine,
        content=text(model.content, warnings, 2000) if include_messages else None,
        attachment_count=len(model.attachments),
    )


def project_vendor_visit_conversation(
    model: VisitConversation, *, include_messages: bool = False, offset: int = 0, limit: int = 25
) -> tuple[VisitConversationData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN", "TIMESTAMP_UNITS_UNVERIFIED"]
    return VisitConversationData(
        visit_id=identity(model.visit_id, warnings),
        thread_id=identity(model.thread_id, warnings),
        window=_window(model.window, warnings),
        calls_enabled=model.calls_enabled,
        live_call_present=model.live_call is not None,
        unread_count=model.unread_count,
        participants=[
            ParticipantSummary(
                role=text(item.role, warnings),
                vendor_id=identity(item.vendor_id, warnings),
                display_name=text(item.display_name, warnings),
                is_me=item.is_me,
            )
            for item in nested(model.participants, warnings)
        ],
        page=local_page(
            model.messages,
            lambda item: _message(item, include_messages, warnings),
            warnings,
            offset,
            limit,
        ),
    ), warnings


def project_help_center_bundle(
    model: HelpCenterBundleResponse,
    *,
    kind: Literal["topics", "articles"] = "topics",
    include_body: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> tuple[HelpCenterData, list[str]]:
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    bundle = model.data
    if kind == "topics":
        return HelpCenterData(
            app=text(bundle.app, warnings),
            kind=kind,
            page=local_page(
                bundle.topics,
                lambda item: HelpTopicSummary(
                    id=identity(item.id, warnings),
                    slug=identity(item.slug, warnings),
                    name=text(item.name, warnings),
                    blurb=text(item.blurb, warnings, 2000),
                    system_image=text(item.system_image, warnings),
                    sort_order=item.sort_order,
                ),
                warnings,
                offset,
                limit,
            ),
        ), warnings
    return HelpCenterData(
        app=text(bundle.app, warnings),
        kind=kind,
        page=local_page(
            bundle.articles,
            lambda item: HelpArticleSummary(
                id=identity(item.id, warnings),
                topic_id=identity(item.topic_id, warnings),
                slug=identity(item.slug, warnings),
                sort_order=item.sort_order,
                is_top_question=item.is_top_question,
                is_featured=item.is_featured,
                article_version_id=identity(item.article_version_id, warnings),
                version_number=item.version_number,
                title=text(item.title, warnings),
                summary=text(item.summary, warnings, 2000),
                body_markdown=text(item.body_markdown, warnings, 2000) if include_body else None,
            ),
            warnings,
            offset,
            limit,
        ),
    ), warnings


# Only plain heading labels are surfaced. Share messages, button copy and any
# unknown key are omitted, since they're the keys most likely to embed the
# referral URL or other people's data. pill_symbol is an icon name, not useful
# text, so it stays out.
REFERRAL_DISPLAY_KEYS = ("title", "description", "pill_text", "fine_print")


def project_referral_code(model: ReferralCodeResponse) -> tuple[ReferralCodeData, list[str]]:
    """Code, allowlisted display labels and a referred-home count. Never the referral URL.

    Display keys and referred-home items aren't verified. Only string labels
    under REFERRAL_DISPLAY_KEYS survive. Referred homes may describe other
    people and are counted only.
    """
    warnings: list[str] = []
    referral = model.referral_code
    if referral.model_extra:
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
    if referral.referred_homes:
        _warn(warnings, "OPAQUE_ITEMS_OMITTED")
    labels: list[ReferralLabel] = []
    if set(referral.display) - set(REFERRAL_DISPLAY_KEYS):
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
    for key in REFERRAL_DISPLAY_KEYS:
        value = referral.display.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            _warn(warnings, "OPAQUE_FIELDS_OMITTED")
            continue
        labels.append(ReferralLabel(key=key, value=text(value, warnings)))
    return ReferralCodeData(
        code=text(referral.code, warnings),
        display=labels,
        referred_home_count=len(referral.referred_homes),
    ), warnings


# Card props vary by template. Only these keys are read. Colors, images,
# visual_* styling and every other key are omitted, never dumped.
FEED_TEXT_PROPS = ("title", "feature_name", "button_caption")
FEED_BRIEF_PROPS = ("subtitle",)
FEED_ACTION_PROPS = ("action", "button_action")
FEED_COUNT_PROPS = ("completed_count", "total_count")
FEED_PROPS = FEED_TEXT_PROPS + FEED_BRIEF_PROPS + FEED_ACTION_PROPS + FEED_COUNT_PROPS


def _prop_text(
    props: Mapping[str, object], key: str, warnings: list[str], maximum: int = 256
) -> str | None:
    value = props.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
        return None
    return text(value, warnings, maximum)


def _prop_action(props: Mapping[str, object], key: str, warnings: list[str]) -> str | None:
    """A bare token like open_inventory. URLs, deep links and objects are dropped."""
    value = props.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
        return None
    return identity(value, warnings)


def _prop_count(props: Mapping[str, object], key: str, warnings: list[str]) -> int | None:
    value = props.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
        return None
    return value


def _feed_card(card: HomeFeedCard, warnings: list[str]) -> FeedCardSummary:
    props = card.props
    if set(props) - set(FEED_PROPS) or card.model_extra:
        _warn(warnings, "OPAQUE_FIELDS_OMITTED")
    if card.children:
        _warn(warnings, "OPAQUE_ITEMS_OMITTED")
    return FeedCardSummary(
        id=identity(card.id, warnings),
        template_id=identity(card.template_id, warnings),
        name=text(card.name, warnings),
        title=_prop_text(props, "title", warnings),
        subtitle=_prop_text(props, "subtitle", warnings, 2000),
        feature_name=_prop_text(props, "feature_name", warnings),
        button_caption=_prop_text(props, "button_caption", warnings),
        action=_prop_action(props, "action", warnings),
        button_action=_prop_action(props, "button_action", warnings),
        completed_count=_prop_count(props, "completed_count", warnings),
        total_count=_prop_count(props, "total_count", warnings),
        show_starts_at_minutes_after_onboarding=card.show_starts_at_minutes_after_onboarding,
        show_ends_at_minutes_after_onboarding=card.show_ends_at_minutes_after_onboarding,
        child_count=len(card.children),
    )


def project_home_feed(
    model: HomeFeedResponse, *, offset: int = 0, limit: int = 25
) -> tuple[HomeFeedData, list[str]]:
    """Allowlisted card text, safe action tokens, counts and show windows.

    Nested children are counted, never projected. Their shape is unobserved.
    """
    warnings = ["UPSTREAM_COMPLETENESS_UNKNOWN"]
    return HomeFeedData(
        page=local_page(
            model.cards, lambda card: _feed_card(card, warnings), warnings, offset, limit
        )
    ), warnings
