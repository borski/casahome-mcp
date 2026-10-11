"""Stage-zero compatibility/privacy proof against the real, locked MCP SDK."""

from typing import Annotated

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from casahome_mcp.validation import input_guard


class Answer(BaseModel):
    value: int


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_compatibility_and_private_validation(
    mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    server = MCPServer("Proof")
    server.middleware.append(input_guard(server))

    @server.tool(structured_output=True)
    async def proof(n: Annotated[int, Field(ge=1, le=5)], ctx: Context) -> Answer:
        if n == 5:
            raise ToolError("EXPECTED: Fixed failure.")
        return Answer(value=n)

    async with Client(server, mode=mode) as client:
        result = await client.call_tool("proof", {"n": 2})
        assert not result.is_error
        assert result.structured_content == {"value": 2}
        error = await client.call_tool("proof", {"n": 5})
        assert error.is_error
        marker = "fake-credential-that-must-not-appear"
        for arguments in ({}, {"n": marker}, {"n": 0}, {"n": 2, "extra": marker}):
            result = await client.call_tool("proof", arguments)
            assert result.is_error
            assert marker not in result.model_dump_json()
            assert "INVALID_ARGUMENT" in result.model_dump_json()
        assert marker not in caplog.text
