"""Refuse invalid tool input before SDK error formatting can echo caller values.

Uses the documented MCP v2 middleware API, without changing protocol handlers.
This API is provisional. The locked SDK version and protocol tests are essential.
"""

import json
from copy import deepcopy
from typing import Any
from unicodedata import category
from uuid import UUID

from jsonschema import Draft202012Validator
from mcp.server import MCPServer, ServerRequestContext
from mcp.server.context import CallNext, HandlerResult, ServerMiddleware
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from .actions.models import CONTENT_FIELDS


def safe_strings(value: object, content_fields: set[str], field: str = "") -> bool:
    if isinstance(value, str):
        return not any(
            category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            and not (field in content_fields and char in "\n\r\t")
            for char in value
        )
    if isinstance(value, dict):
        return all(
            isinstance(key, str)
            and safe_strings(key, set())
            and safe_strings(item, content_fields, key)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return all(safe_strings(item, content_fields, field) for item in value)
    return True


def input_guard(
    server: MCPServer,
    action_validators: dict[str, FuncMetadata] | None = None,
) -> ServerMiddleware[Any]:
    async def guard(ctx: ServerRequestContext[Any], call_next: CallNext) -> HandlerResult:
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = ctx.params
        if not isinstance(params, dict):
            return refusal()
        tools = {tool.name: tool for tool in await server.list_tools()}
        name = params.get("name")
        if not isinstance(name, str) or name not in tools:
            return refusal()
        schema = deepcopy(tools[name].input_schema)
        schema["additionalProperties"] = False
        arguments = params.get("arguments", {})
        # Content-only multiline allowance is tool-specific and recursive.
        if not safe_strings(arguments, CONTENT_FIELDS.get(name, set())):
            return refusal()
        if isinstance(arguments, dict):
            # JSON Schema accepts 1.0 as an integer, strict Pydantic doesn't.
            for key in ("offset", "limit", "page", "page_size", "upstream_limit"):
                if (
                    key in arguments
                    and arguments[key] is not None
                    and type(arguments[key]) is not int
                ):
                    return refusal()
            for key in ("brand_id", "collection_id"):
                if key in arguments and type(arguments[key]) not in (str, int):
                    return refusal()
            for key in ("cursor", "before"):
                value = arguments.get(key)
                if isinstance(value, str) and value.lower().startswith(("//", "../", "www.")):
                    return refusal()
            # MCP pre-parses JSON strings for union-typed arguments. Constrain
            # UUIDs to canonical dashed strings before that preprocessing can
            # turn an object/string/number into an invalid union input.
            for key in ("home_id", "entity_id", "room_id", "target_id"):
                value = arguments.get(key)
                if value is not None:
                    if not isinstance(value, str):
                        return refusal()
                    try:
                        if value.lower() != str(UUID(value)):
                            return refusal()
                    except ValueError:
                        return refusal()
            # Nullable exact filters must not be reinterpreted as JSON objects,
            # arrays or null by MCP's union preprocessing. Refuse ambiguous input.
            for key in (
                "room",
                "category",
                "q",
                "search",
                "document_type",
                "cursor",
                "before",
                "todo_id",
                "task_id",
                "request_id",
                "brand_id",
                "collection_id",
                "document_id",
                "availability_request_id",
                "visit_id",
                "include_current_vendor_visit_id",
                "plan_id",
                "enum_type",
                "app_id",
            ):
                value = arguments.get(key)
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                    except (ValueError, RecursionError):
                        continue
                    if parsed is None or isinstance(parsed, dict | list):
                        return refusal()
        if not Draft202012Validator(schema).is_valid(arguments):
            return refusal()
        if action_validators is not None and name in action_validators:
            try:
                # Actual MCP v2 JSON-string preprocessing and argument codec,
                # before MCP's Pydantic error formatter can echo input values.
                action_validators[name].validate_arguments(arguments)
            except (ValidationError, ValueError, TypeError, RecursionError):
                return refusal()
        return await call_next(ctx)

    return guard


def refusal() -> CallToolResult:
    return CallToolResult(
        is_error=True,
        content=[TextContent(type="text", text="INVALID_ARGUMENT: Check the tool input schema.")],
    )
