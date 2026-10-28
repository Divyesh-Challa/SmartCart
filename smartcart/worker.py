"""
Standalone background worker. In production run this as its own process
(with SMARTCART_RUN_SCHEDULER=false on the web service) so the periodic sync
runs exactly once no matter how many web workers are serving requests.

    python -m smartcart.worker
"""

import asyncio
import logging

from smartcart.config import get_settings
from smartcart.database import bootstrap_database
from smartcart.observability import configure_observability
from smartcart.scheduler import background_sync_worker


def main() -> None:
    configure_observability(get_settings())
    logging.getLogger("smartcart").info("Worker starting: %s", bootstrap_database())
    asyncio.run(background_sync_worker())


if __name__ == "__main__":
    main()
