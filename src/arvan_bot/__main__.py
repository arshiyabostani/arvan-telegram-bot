from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import __version__
from .bot.app import ALLOWED_UPDATES, build_application
from .config import ConfigError, Settings
from .logging_setup import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arvan-bot", description="Telegram bot for ArvanCloud CDN")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--check-config", action="store_true", help="validate the environment and exit")
    args = parser.parse_args(argv)

    load_dotenv(Path.cwd() / ".env")
    try:
        settings = Settings.from_env(os.environ)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.check_config:
        print("configuration OK")
        return 0

    configure_logging(settings.log_level, settings.secrets)
    log = logging.getLogger("arvan_bot")
    log.info(
        "starting v%s (users=%d, domains=%s, read_only=%s)",
        __version__,
        len(settings.allowed_user_ids),
        ",".join(sorted(settings.allowed_domains)) or "all",
        settings.read_only,
    )
    app = build_application(settings)
    # Updates queued while the bot was offline are dropped: nobody should have an
    # old "confirm" tap replayed minutes or hours later.
    app.run_polling(allowed_updates=ALLOWED_UPDATES, drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
