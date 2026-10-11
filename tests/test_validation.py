import pytest
from mcp import Client

from casahome_mcp.config import ConfiguredHome, Settings
from casahome_mcp.server import create_server

HOME = "11111111-1111-4111-8111-111111111111"
MARKER = "synthetic-validation-secret"


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize(
    "argument",
    [
        {"home_id": '{"secret":"' + MARKER + '"}'},
        {"home_id": '["' + MARKER + '"]'},
        {"home_id": "null"},
        {"home_id": HOME.replace("-", "")},
        {"offset": 1.0},
        {"limit": 25.0},
    ],
)
async def test_preprocessing_differences_fail_closed(
    mode: str, argument: dict[str, object], caplog: pytest.LogCaptureFixture
) -> None:
    server = create_server(Settings(homes=(ConfiguredHome(id=HOME, label="Test"),)))
    async with Client(server, mode=mode) as client:
        result = await client.call_tool("casa_list_inventory", argument)
        assert result.is_error
        assert "INVALID_ARGUMENT" in result.model_dump_json()
        assert "input_value" not in result.model_dump_json()
        assert MARKER not in result.model_dump_json()
        assert MARKER not in caplog.text
