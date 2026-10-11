"""Stdio entry point. Settings and sessions are created only when launched."""

import sys

from .config import ConfigurationError, Settings
from .errors import configure_logging
from .server import create_server


def main() -> None:
    configure_logging()
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    create_server(settings).run(transport="stdio")


if __name__ == "__main__":
    main()
