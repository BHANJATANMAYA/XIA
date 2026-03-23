"""
main.py — xia entry point (Part 10: Final, hardened)
"""

import sys
import os

from core.config import cfg
from core.logger import get_logger, setup_logging
from core.paths import PATHS

setup_logging(
    level=cfg.logging.level,
    log_to_file=cfg.logging.log_to_file,
    max_bytes=cfg.logging.max_log_size_mb * 1024 * 1024,
    backup_count=cfg.logging.backup_count,
)

log = get_logger(__name__)


def main():
    log.info("xia starting — Part 10 (final)")
    log.info("Root: %s | Model: %s | Python: %s",
             PATHS.root, cfg.llm.model, sys.version.split()[0])

    if sys.platform == "win32":
        os.system("")

    try:
        from interface.cli import CLI
        CLI().run()
    except KeyboardInterrupt:
        print("\n  Goodbye.\n")
        sys.exit(0)
    except ImportError as e:
        log.error("CLI failed to load: %s", e)
        print(f"\n  Error loading CLI: {e}")
        print("  Ensure all Part 9 files are in place.\n")
        sys.exit(1)
    except Exception as e:
        log.exception("Fatal startup error")
        from core.errors import handle_error
        handle_error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
