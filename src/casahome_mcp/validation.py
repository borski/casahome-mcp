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
from mcp.types import CallToolResult, TextContent


def input_guard(server: MCPServer) -> ServerMiddleware[Any]:
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
        # Python JSON Schema regexes accept a trailing newline at '$', while
        # Pydantic's Rust regex engine rejects it and echoes the rejected value.
        # All exposed string inputs are identifiers/dates/filters, never multiline text.
        if isinstance(arguments, dict) and any(
            isinstance(value, str) and any(category(char) in {"Cc", "Cf"} for char in value)
            for value in arguments.values()
        ):
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
        return await call_next(ctx)

    return guard


def refusal() -> CallToolResult:
    return CallToolResult(
        is_error=True,
        content=[TextContent(type="text", text="INVALID_ARGUMENT: Check the tool input schema.")],
    )
