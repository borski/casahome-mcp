"""Refuse invalid tool input before SDK error formatting can echo caller values.

Uses the documented MCP v2 middleware API, without changing protocol handlers.
This API is provisional. The locked SDK version and protocol tests are essential.
"""

from copy import deepcopy
from typing import Any
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
        # All exposed string inputs are identifiers/dates, never multiline text.
        if isinstance(arguments, dict) and any(
            isinstance(value, str) and any(ord(char) < 32 or ord(char) == 127 for char in value)
            for value in arguments.values()
        ):
            return refusal()
        if isinstance(arguments, dict):
            # JSON Schema accepts 1.0 as an integer, strict Pydantic doesn't.
            for key in ("offset", "limit"):
                if key in arguments and type(arguments[key]) is not int:
                    return refusal()
            # MCP pre-parses JSON strings for union-typed arguments. Constrain
            # home_id to a canonical dashed UUID before that preprocessing can
            # turn an object/string/number into an invalid union input.
            home = arguments.get("home_id")
            if home is not None:
                if not isinstance(home, str):
                    return refusal()
                try:
                    if home.lower() != str(UUID(home)):
                        return refusal()
                except ValueError:
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
