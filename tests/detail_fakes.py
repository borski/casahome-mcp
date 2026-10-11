"""Explicit typed SDK detail fakes. All values synthetic, no socket access."""

from casahome.const import CASA_APP_BUILD
from casahome.models.assets import ReleaseNotesResponse
from casahome.models.availability import MemberAvailabilityDetail
from casahome.models.catalogs import InventoryEnumsResponse
from casahome.models.documents import (
    DocumentDetailsResponse,
    DocumentStructureSuggestionsResponse,
    DocumentSuggestionsResponse,
)
from casahome.models.feed import HomeFeedResponse
from casahome.models.help_center import HelpCenterBundleResponse
from casahome.models.membership import MembershipDetails, MembershipSavings
from casahome.models.paint import InventoryPaintMatchesResponse
from casahome.models.purchases import ScopedPurchasesResponse
from casahome.models.referral import ReferralCodeResponse
from casahome.models.tasks import BookableHandymanTasksResponse, GroupedTaskDetails, TaskDetails
from casahome.models.visits import VendorVisitDetails, VisitCallsResponse, VisitConversation

SECRET = "synthetic-secret-never-output"
URL = "https://example.invalid/signed?token=" + SECRET
UPDATE_TEXT = "Synthetic optional update message."
VISIT_TEXT = "Synthetic optional visit message."
EXCERPT_TEXT = "Synthetic optional document suggestion excerpt."
NOTE_TEXT = "Synthetic optional scoped purchase return note."
BODY_TEXT = "Synthetic optional help article body."
REFERRAL_LABEL = "Synthetic referral title"
RELEASE_TEXT = "Synthetic release content"
PRELUDE_TEXT = "Synthetic prelude"
FEED_TITLE = "Synthetic feed title"


class DetailFake:
    async def _before(self, name: str, *args: object) -> None:
        raise NotImplementedError

    def init_details(self) -> None:
        self.bookable = BookableHandymanTasksResponse.model_validate(
            {
                "items": [{"kind": "task", "id": SECRET}, {"unknown": URL}, SECRET, None],
                "current_vendor_additional_availability_minutes": 0,
                "total_additional_availability_minutes": 90,
                "secret": SECRET,
            }
        )
        self.membership = MembershipDetails.model_validate(
            {
                "name": "Synthetic membership",
                "amount": SECRET,
                "amount_cents": 123456,
                "interval": SECRET,
                "next_billing_date": 2222,
                "member_since": 1111,
                "benefits": [
                    {
                        "id": {"private": SECRET},
                        "title": "Synthetic benefit",
                        "emoji": "!",
                        "symbol": "star",
                        "description": "Synthetic description",
                        "secret": SECRET,
                    }
                ],
                "owner": SECRET,
                "payment": SECRET,
                "address": SECRET,
            }
        )
        self.savings = MembershipSavings.model_validate(
            {
                "home_id": SECRET,
                "calculated_at": "synthetic-calculation-time",
                "should_promote": False,
                "summary": {"total_time_saved_seconds": 0, "total_money_saved_cents": 150},
                "categories": [
                    {
                        "type": "synthetic",
                        "label": "Synthetic category",
                        "color": "blue",
                        "preview": None,
                        "is_visible": False,
                        "time_saved_seconds": 0,
                        "money_saved_cents": 150,
                        "breakdown": [{"title": "One", "value": "Zero"}],
                    }
                ],
                "metadata": {"id": SECRET, "created_at": SECRET, "updated_at": SECRET},
            }
        )
        self.enums = InventoryEnumsResponse.model_validate(
            {
                "enums": [
                    {
                        "id": "enum-one",
                        "type": "synthetic",
                        "name": "Synthetic option",
                        "symbol_name": "star",
                        "category": "Synthetic",
                        "icon_url": URL,
                        "secret": SECRET,
                    }
                ]
            }
        )
        self.release_notes = ReleaseNotesResponse.model_validate(
            {
                "data": [
                    {
                        "id": "note-one",
                        "title": "Synthetic release",
                        "version": "synthetic-v1",
                        "date": 1111,
                        "min_build_number": 1,
                        "max_build_number": 2,
                        "prelude": PRELUDE_TEXT,
                        "hero_image_url": URL,
                        "sections": [
                            {
                                "id": "section-one",
                                "title": "Synthetic section",
                                "content": RELEASE_TEXT,
                                "hero_image_url": URL,
                            }
                        ],
                    }
                ]
            }
        )
        self.availability = MemberAvailabilityDetail.model_validate(
            {
                "availability_request": {
                    "id": "availability-one",
                    "request_id": "request-one",
                    "home_id": SECRET,
                    "status": "future-status",
                    "slot_count": 1,
                    "created_at": 1,
                },
                "slots": [
                    {
                        "id": "slot-one",
                        "member_availability_request_id": "availability-one",
                        "start_time": 2,
                        "end_time": 3,
                    }
                ],
                "home_timezone": "Synthetic timezone",
                "constraints": {
                    "snap_minutes": 15,
                    "min_slot_minutes": 30,
                    "default_duration_minutes": 60,
                    "lead_time_minutes": 120,
                },
                "address": SECRET,
            }
        )
        self.document = DocumentDetailsResponse.model_validate(
            {
                "document": {
                    "id": "doc-one",
                    "name": "Synthetic document",
                    "document_type": "warranty",
                    "size_bytes": 42,
                    "original_filename": SECRET,
                    "uploaded_by_name": SECRET,
                    "home_id": SECRET,
                    "url": URL,
                    "owner": SECRET,
                    "organization": {"status": "future-status", "error_code": SECRET},
                }
            }
        )
        citation = {"page_index": 0, "page_label": "one", "excerpt": EXCERPT_TEXT, "url": URL}
        self.doc_suggestions = DocumentSuggestionsResponse.model_validate(
            {
                "suggestions": [
                    {
                        "id": "suggestion-one",
                        "todo_id": "todo-one",
                        "title": "Synthetic suggestion",
                        "action": "future-action",
                        "reason": "Synthetic reason",
                        "citations": [citation],
                        "state": "future-state",
                        "work_deleted": False,
                        "task_id": None,
                        "request_id": None,
                        "secret": SECRET,
                    }
                ],
                "analysis_status": "future-status",
                "limitations": ["Synthetic limitation"],
                "url": URL,
            }
        )
        self.structure_suggestions = DocumentStructureSuggestionsResponse.model_validate(
            {
                "suggestions": [
                    {
                        "id": "structure-one",
                        "section": "synthetic",
                        "title": "Synthetic structure",
                        "current_values": ["one"],
                        "current_label": "Current",
                        "proposed_label": "Proposed",
                        "reason": "Synthetic reason",
                        "state": "future-state",
                        "changed_since_analysis": False,
                        "citations": [citation],
                        "secret": SECRET,
                    }
                ]
            }
        )
        self.paint_matches = InventoryPaintMatchesResponse.model_validate(
            {
                "matches": [
                    {
                        "id": 0,
                        "color_name": "Synthetic color",
                        "brand_name": "Synthetic brand",
                        "color_hex": "#112233",
                        "closeness_percentage": 0.0,
                        "url": URL,
                    }
                ],
                "is_manually_added": False,
            }
        )
        purchase = {
            "id": "purchase-one",
            "title": "Synthetic purchase",
            "quantity": 0,
            "unit_price_usd_cents": 0,
            "vendor": {"id": "vendor-one", "name": "Synthetic vendor", "image_url": URL},
            "return_policy_notes": NOTE_TEXT,
            "purchase_link": URL,
            "member_pricing_summary": {"secret": SECRET},
            "invoice_id": SECRET,
            "return_info": {"private": SECRET},
        }
        self.scoped_purchases = ScopedPurchasesResponse.model_validate(
            {
                "context_title": "Synthetic scoped purchases",
                "pending_purchase_approvals": [purchase],
                "approved_purchases": [{**purchase, "approved_at": 2, "is_voided": False}],
                "purchased_items": [{**purchase, "purchased_at": 3}],
                "payment": SECRET,
            }
        )
        update = {
            "id": "update-one",
            "message": UPDATE_TEXT,
            "sender_name": "Synthetic sender",
            "sent_at": 2,
            "sender_avatar_url": URL,
            "attachments": [],
            "secret": SECRET,
        }
        visit = {"id": "visit-one", "start_time": 1}
        self.task = TaskDetails.model_validate(
            {
                "id": "task-one",
                "title": "Synthetic task",
                "description": "Synthetic description",
                "emoji": "!",
                "status": "future-status",
                "visit": visit,
                "updates": [update],
                "attachments": [],
                "can_schedule_handyman_vendor_visit": False,
                "can_chat_with_concierge": False,
                "can_edit": False,
                "can_delete": False,
                "secret": SECRET,
            }
        )
        window = {
            "state": "future-state",
            "opens_at": 1,
            "closes_at": 2,
            "closed_reason": None,
            "url": URL,
        }
        self.visit_details = VendorVisitDetails.model_validate(
            {
                "id": "visit-one",
                "type": "future-type",
                "status": "future-status",
                "request": {
                    "id": "request-one",
                    "type": "future-type",
                    "status": "future-status",
                    "title": "Synthetic request",
                    "emoji": "!",
                    "has_unread_messages": False,
                    "message_preview": {
                        "sender_name": "Synthetic sender",
                        "sent_at": 2,
                        "message": VISIT_TEXT,
                    },
                },
                "calendar_event": {"id": "event-one", "start_time": 1, "end_time": 2},
                "vendors": [
                    {
                        "id": "vendor-one",
                        "display_name": "Synthetic vendor",
                        "compact_display_name": "Vendor",
                        "type": "future-type",
                        "image_url": URL,
                        "phone": SECRET,
                        "location": SECRET,
                    }
                ],
                "task_items": [{"kind": "known-looking-tag", "secret": SECRET}],
                "invoices": [
                    {
                        "id": SECRET,
                        "vendor_name": SECRET,
                        "amount_display": SECRET,
                        "user_collection_status": SECRET,
                        "status": SECRET,
                    }
                ],
                "purchases": [{"id": SECRET, "status": SECRET, "image_url": URL}],
                "can_add_remove_items": False,
                "can_cancel": False,
                "feedback": {"secret": SECRET},
                "conversation": {
                    "thread_id": "thread-one",
                    "window": window,
                    "counterparties": [],
                    "unread_count": 0,
                    "latest_message": {
                        "sender_display_name": "Synthetic sender",
                        "sent_at": 1,
                        "message": VISIT_TEXT,
                    },
                },
            }
        )
        self.visit_plan = GroupedTaskDetails.model_validate(
            {
                "plan": {
                    "id": "plan-one",
                    "title": "Synthetic plan",
                    "description": "Synthetic description",
                    "emoji": "!",
                },
                "visit": visit,
                "tasks": [
                    {
                        "id": "task-one",
                        "status": "future-status",
                        "updates": [update],
                        "target": {
                            "id": "target-one",
                            "kind": "future-kind",
                            "primary_label": "Primary",
                            "secondary_label": "Secondary",
                            "symbol_name": "star",
                            "image_url": URL,
                        },
                    }
                ],
                "secret": SECRET,
            }
        )
        self.calls_result = VisitCallsResponse.model_validate(
            {
                "calls": [
                    {
                        "id": "call-one",
                        "vendor_visit_id": "visit-one",
                        "status": "future-status",
                        "started_by_user_id": SECRET,
                        "started_by_role": "vendor",
                        "started_at": 1,
                        "answered_at": 2,
                        "ended_at": 3,
                        "duration_seconds": 0,
                        "recorded": False,
                        "participants": [
                            {"user_id": SECRET, "role": "vendor", "rang_at": 1, "phone": SECRET}
                        ],
                        "join_url": URL,
                        "access_grant": SECRET,
                        "phone": SECRET,
                    }
                ]
            }
        )
        self.conversation = VisitConversation.model_validate(
            {
                "visit_id": "visit-one",
                "thread_id": "thread-one",
                "window": window,
                "calls_enabled": False,
                "unread_count": 0,
                "participants": [
                    {
                        "user_id": SECRET,
                        "role": "vendor",
                        "vendor_id": "vendor-one",
                        "display_name": "Synthetic participant",
                        "is_me": False,
                        "avatar_url": URL,
                    }
                ],
                "messages": [
                    {
                        "id": "message-one",
                        "thread_id": "thread-one",
                        "created_at": 1,
                        "sender_role": "vendor",
                        "sender_user_id": SECRET,
                        "sender_display_name": "Synthetic sender",
                        "is_mine": False,
                        "content": VISIT_TEXT,
                        "sender_avatar_url": URL,
                        "attachments": [],
                        "parts": [{"type": "text", "text": SECRET}, URL, None],
                        "private": SECRET,
                    }
                ],
                "event_cursor": SECRET,
                "join_url": URL,
            }
        )
        self.help_bundle = HelpCenterBundleResponse.model_validate(
            {
                "data": {
                    "app": "synthetic-app",
                    "topics": [
                        {
                            "id": "topic-one",
                            "slug": "synthetic-topic",
                            "name": "Synthetic topic",
                            "blurb": "Synthetic blurb",
                            "systemImage": "star",
                            "heroImageURL": URL,
                            "sortOrder": 0,
                        }
                    ],
                    "articles": [
                        {
                            "id": "article-one",
                            "topicId": "topic-one",
                            "slug": "synthetic-article",
                            "sortOrder": 0,
                            "isTopQuestion": False,
                            "isFeatured": False,
                            "articleVersionId": "version-one",
                            "versionNumber": 1,
                            "title": "Synthetic article",
                            "summary": "Synthetic summary",
                            "bodyMarkdown": BODY_TEXT,
                            "url": URL,
                        }
                    ],
                }
            }
        )
        self.referral = ReferralCodeResponse.model_validate(
            {
                "referral_code": {
                    "code": "SYNTHCODE",
                    "referral_url": URL,
                    "display": {
                        "title": REFERRAL_LABEL,
                        "share_message": "Join me " + URL,
                        "nested": {"secret": SECRET},
                        "bad key": "Synthetic",
                    },
                    "referred_homes": [{"address": SECRET}, {"name": SECRET}],
                    "secret": SECRET,
                }
            }
        )
        self.feed = HomeFeedResponse.model_validate(
            {
                "cards": [
                    {
                        "id": "card-one",
                        "template_id": "home_onboarding",
                        "name": "Home Onboarding",
                        "props": {
                            "title": FEED_TITLE,
                            "subtitle": "Synthetic subtitle",
                            "feature_name": "Synthetic feature",
                            "button_caption": "Continue",
                            "button_action": "open_onboarding",
                            "button_symbol": "star",
                            "action": URL,
                            "completed_count": 2,
                            "total_count": 5,
                            "image": URL,
                            "colors": {"background": "#" + SECRET},
                            "visual_style": {"secret": SECRET},
                        },
                        "show_starts_at_minutes_after_onboarding": 0,
                        "show_ends_at_minutes_after_onboarding": None,
                        "children": [],
                        "secret": SECRET,
                    },
                    {
                        "id": "card-two",
                        "template_id": "release_notes",
                        "name": "Release Notes",
                        "props": {
                            "title": "Join " + URL,
                            "subtitle": {"secret": SECRET},
                            "completed_count": True,
                            "total_count": "5",
                        },
                        "show_starts_at_minutes_after_onboarding": 60,
                        "show_ends_at_minutes_after_onboarding": 120,
                        "children": [
                            {
                                "id": "child-one",
                                "template_id": "nested",
                                "name": SECRET,
                                "props": {"title": SECRET},
                                "show_starts_at_minutes_after_onboarding": 0,
                                "children": [],
                            }
                        ],
                    },
                ]
            }
        )

    async def bookable_handyman_tasks(
        self, home_id: str, *, include_current_vendor_visit_id: str | None = None
    ) -> BookableHandymanTasksResponse:
        await self._before("bookable_handyman_tasks", home_id, include_current_vendor_visit_id)
        return self.bookable

    async def membership_info(self, home_id: str) -> MembershipDetails:
        await self._before("membership_info", home_id)
        return self.membership

    async def membership_savings(self, home_id: str) -> MembershipSavings:
        await self._before("membership_savings", home_id)
        return self.savings

    async def inventory_enums(self, enum_type: str) -> InventoryEnumsResponse:
        await self._before("inventory_enums", enum_type)
        return self.enums

    async def release_notes_diff(
        self, *, current_build: int = CASA_APP_BUILD
    ) -> ReleaseNotesResponse:
        assert current_build == CASA_APP_BUILD
        await self._before("release_notes_diff")
        return self.release_notes

    async def availability_request_details(
        self, home_id: str, availability_request_id: str
    ) -> MemberAvailabilityDetail:
        await self._before("availability_request_details", home_id, availability_request_id)
        return self.availability

    async def document_details(self, home_id: str, document_id: str) -> DocumentDetailsResponse:
        await self._before("document_details", home_id, document_id)
        return self.document

    async def document_suggestions(
        self, home_id: str, document_id: str, *, view: str | None = None
    ) -> DocumentSuggestionsResponse:
        await self._before("document_suggestions", home_id, document_id, view)
        return self.doc_suggestions

    async def document_structure_suggestions(
        self, home_id: str, document_id: str
    ) -> DocumentStructureSuggestionsResponse:
        await self._before("document_structure_suggestions", home_id, document_id)
        return self.structure_suggestions

    async def inventory_paint_matches(
        self, home_id: str, entity_id: str
    ) -> InventoryPaintMatchesResponse:
        await self._before("inventory_paint_matches", home_id, entity_id)
        return self.paint_matches

    async def request_purchases(self, home_id: str, request_id: str) -> ScopedPurchasesResponse:
        await self._before("request_purchases", home_id, request_id)
        return self.scoped_purchases

    async def task_details(self, home_id: str, task_id: str) -> TaskDetails:
        await self._before("task_details", home_id, task_id)
        return self.task

    async def vendor_visit_details(self, home_id: str, visit_id: str) -> VendorVisitDetails:
        await self._before("vendor_visit_details", home_id, visit_id)
        return self.visit_details

    async def vendor_visit_autopilot_plan(
        self, home_id: str, visit_id: str, plan_id: str
    ) -> GroupedTaskDetails:
        await self._before("vendor_visit_autopilot_plan", home_id, visit_id, plan_id)
        return self.visit_plan

    async def vendor_visit_calls(self, home_id: str, visit_id: str) -> VisitCallsResponse:
        await self._before("vendor_visit_calls", home_id, visit_id)
        return self.calls_result

    async def vendor_visit_conversation(self, home_id: str, visit_id: str) -> VisitConversation:
        await self._before("vendor_visit_conversation", home_id, visit_id)
        return self.conversation

    async def vendor_visit_purchases(self, home_id: str, visit_id: str) -> ScopedPurchasesResponse:
        await self._before("vendor_visit_purchases", home_id, visit_id)
        return self.scoped_purchases

    async def help_center_bundle(self, app_id: str) -> HelpCenterBundleResponse:
        await self._before("help_center_bundle", app_id)
        return self.help_bundle

    async def referral_code(self) -> ReferralCodeResponse:
        await self._before("referral_code")
        return self.referral

    async def home_feed(self, home_id: str, *, app_build: int = CASA_APP_BUILD) -> HomeFeedResponse:
        assert app_build == CASA_APP_BUILD
        await self._before("home_feed", home_id)
        return self.feed
