"""Value-free tool failures and stderr diagnostics."""

import logging
import sys

from casahome import CasaApiError, CasaAuthError, CasaConnectionError, CasaResponseError
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from .projections import ProjectionError

MESSAGES = {
    "INVALID_ARGUMENT": "Check the tool input schema.",
    "HOME_REQUIRED": "Select a home from casa_list_homes.",
    "NO_HOMES_CONFIGURED": "The operator must configure CASA_HOMES_JSON.",
    "HOME_NOT_ALLOWED": "Select a configured home from casa_list_homes.",
    "UNVERIFIED_DISABLED": "The operator controls CASA_ALLOW_UNVERIFIED_READS.",
    "AUTH_NOT_CONFIGURED": "The operator must inject a Casa credential securely.",
    "AUTH_FAILED": "The operator must securely reprovision the credential.",
    "SCHEMA_MISMATCH": "Review the SDK contract against traffic. Raw fallback is disabled.",
    "UPSTREAM_UNAVAILABLE": "Upstream connectivity failed. No adapter retry was made.",
    "ACCESS_DENIED": "Casa denied access.",
    "NOT_FOUND": "Casa returned not found. No alternate paths were tried.",
    "RATE_LIMITED": "Casa rate-limited the request. No adapter retry was made.",
    "UPSTREAM_ERROR": "Casa returned an error.",
    "TIMEOUT": "The tool deadline expired.",
    "OUTPUT_TOO_LARGE": "Reduce the requested data or page size.",
    "INTERNAL_ERROR": "An internal error occurred.",
}


def failure(code: str) -> ToolError:
    return ToolError(f"{code}: {MESSAGES[code]}")


def mapped_failure(exc: Exception) -> ToolError:
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, CasaAuthError):
        code = "AUTH_FAILED"
    elif isinstance(exc, (CasaResponseError, ValidationError)):
        code = "SCHEMA_MISMATCH"
    elif isinstance(exc, CasaConnectionError):
        code = "UPSTREAM_UNAVAILABLE"
    elif isinstance(exc, CasaApiError):
        code = {403: "ACCESS_DENIED", 404: "NOT_FOUND", 429: "RATE_LIMITED"}.get(
            exc.status, "UPSTREAM_ERROR"
        )
    elif isinstance(exc, ProjectionError):
        code = exc.code
    elif isinstance(exc, TimeoutError):
        code = "TIMEOUT"
    else:
        code = "INTERNAL_ERROR"
        logging.getLogger("casahome_mcp").error("INTERNAL_ERROR: %s", type(exc).__name__)
    return failure(code)


class SafeDiagnostics(logging.Filter):
    """Library exceptions can contain response bodies. Never render them to stderr."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith("casahome_mcp"):
            record.msg = "Library diagnostic omitted."
            record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(SafeDiagnostics())
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
