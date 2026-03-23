"""EkamCore background workers."""

import time

import structlog

logger = structlog.get_logger()


def main() -> None:
    """Placeholder worker process."""
    logger.info("ekamcore_workers_starting")
    while True:
        time.sleep(60)
        logger.info("worker_heartbeat")


if __name__ == "__main__":
    main()
