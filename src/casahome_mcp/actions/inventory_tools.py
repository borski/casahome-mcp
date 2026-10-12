"""Explicit make/model publish and existing-room rename prepares."""

from casahome.models.entity_publish import RenameRoomRequest, SaveAndPublishEntityRequest
from mcp.server.mcpserver import Context
from pydantic import JsonValue

from ..action_protocol import CasaActionsProtocol
from ..runtime import AppContext
from ..tools import EntityId, HomeId
from .core import PREPARE, ActionToolDecorator, build, prepare, preview_body, result
from .models import ActionResult, CatalogName, PathId
from .workflow_tools import gated_description

CATALOG_MATCH_RISK = (
    "Casa matches names against its catalog and may store different canonical names or reject "
    "unknown products. Rejection doesn't prove complete rollback. Reconcile inventory before "
    "any new retry. Never automatically retry or prepare a replacement."
)


def register_inventory_tools(action_tool: ActionToolDecorator) -> None:
    @action_tool(
        description=gated_description(
            "Set an entity's make and/or model. Exactly one ID or name per supplied side, "
            "at least one side. Catalog IDs are canonical UUIDs. Omitted sides aren't sent. "
            "Empty props only, no clears or explicit nulls. " + CATALOG_MATCH_RISK,
            "update_entity_make_model",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_update_entity_make_model(
        entity_id: EntityId,
        ctx: Context[AppContext],
        make_id: EntityId | None = None,
        make_name: CatalogName | None = None,
        model_id: EntityId | None = None,
        model_name: CatalogName | None = None,
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        selections: dict[str, object] = {"props": []}
        for side, id_value, name_value in (
            ("make", make_id, make_name),
            ("model", model_id, model_name),
        ):
            selection = {
                key: value
                for key, value in (("id", id_value), ("name", name_value))
                if value is not None
            }
            if selection:
                selections[side] = selection
        # The actual SDK union rejects both id/name on a side, blank names and
        # an empty selection. No token exists until its body codec accepts this.
        body = build(SaveAndPublishEntityRequest, selections)

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            # Captured strings are immutable. Neither caller nor preview mutation
            # can change the payload that the SDK reconstructs on this one attempt.
            await api.update_entity_make_model(
                home,
                entity_id,
                make_id=make_id,
                make_name=make_name,
                model_id=model_id,
                model_name=model_name,
            )
            return result(home, "update_entity_make_model")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "update_entity_make_model",
            {
                "entity_id": entity_id,
                **body.model_dump(mode="json", exclude_none=True),
                "risk": CATALOG_MATCH_RISK,
            },
            invoke,
        )

    @action_tool(
        description=gated_description(
            "Rename an existing room and set its room type. Both room_type_id and name "
            "are required and sent exactly. Use its current room_type_id to preserve the type. "
            "No room creation or partial update.",
            "rename_room",
        ),
        annotations=PREPARE,
        structured_output=True,
    )
    async def casa_prepare_rename_room(
        room_id: EntityId,
        room_type_id: PathId,
        name: CatalogName,
        ctx: Context[AppContext],
        home_id: HomeId = None,
    ) -> dict[str, JsonValue]:
        body = build(RenameRoomRequest, {"room_type_id": room_type_id, "name": name})

        async def invoke(api: CasaActionsProtocol, home: str) -> ActionResult:
            await api.rename_room(home, room_id, room_type_id=room_type_id, name=name)
            return result(home, "rename_room")

        return prepare(
            ctx.request_context.lifespan_context,
            home_id,
            "rename_room",
            {
                "room_id": room_id,
                **preview_body(body),
                "risk": "Both name and room type are replaced. Use the current room_type_id "
                "to preserve the type. No room is created.",
            },
            invoke,
        )
