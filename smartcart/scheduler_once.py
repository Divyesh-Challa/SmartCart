"""
Run one data sync and exit; for platforms that offer cron jobs but not
always-on workers.

    python -m smartcart.scheduler_once
"""

import logging

from smartcart.config import get_settings
from smartcart.database import bootstrap_database
from smartcart.observability import configure_observability
from smartcart.scheduler import perform_data_sync


def main() -> None:
    configure_observability(get_settings())
    log = logging.getLogger("smartcart")
    log.info("Database ready: %s", bootstrap_database())
    result = perform_data_sync()
    log.info("Sync finished: %s stores, %s prices rebuilt", result["stores_count"], result["inventory_prices_rebuilt"])


if __name__ == "__main__":
    main()
