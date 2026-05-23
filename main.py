"""
main.py — Bot entry point.

Runs the trading loop:
  1. Check market is open
  2. Load latest bars
  3. Run strategy → get signals
  4. Apply risk checks
  5. Execute orders
  6. Sleep until next bar

Usage:
    python main.py
"""

import logging
import time
import os
from datetime import datetime

import config
from broker import AlpacaClient
from data import DataFeed

# ── Logging setup ─────────────────────────────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f"{config.LOG_DIR}/bot_{datetime.now().strftime('%Y%m%d')}.log"
        ),
    ],
)
logger = logging.getLogger("main")


def run():
    logger.info("=" * 50)
    logger.info(f"Bot starting — {'PAPER' if config.ALPACA_PAPER else 'LIVE'} mode")
    logger.info(f"Symbols : {config.SYMBOLS}")
    logger.info("=" * 50)

    client = AlpacaClient()

    # Verify account is healthy before doing anything
    account = client.get_account()
    if account.status != "ACTIVE":
        logger.error(f"Account not active: {account.status}. Exiting.")
        return

    logger.info(f"Portfolio: ${float(account.portfolio_value):,.2f}")
    logger.info(f"Cash     : ${float(account.cash):,.2f}")

    # Phase 2 — initialise data feed and warm up cache
    feed = DataFeed(client)
    logger.info("Warming up data cache...")
    feed.get_history(config.SYMBOLS, days=config.LOOKBACK_DAYS)
    feed.summary()

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        try:
            if not client.is_market_open():
                logger.info("Market closed — sleeping 60s")
                time.sleep(60)
                continue

            # Phase 2: refresh latest bars each tick
            feed.refresh(config.SYMBOLS)

            # TODO (Phase 3): run strategy → signals
            # signals = strategy.compute(feed)

            # TODO (Phase 4): apply risk rules
            # signals = risk_manager.filter(signals, client)

            # TODO (Phase 5): execute orders
            # order_manager.execute(signals, client)

            logger.info("Tick complete — sleeping 60s")
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            break
        except Exception as e:
            logger.exception(f"Unexpected error in main loop: {e}")
            logger.info("Sleeping 30s before retry")
            time.sleep(30)

    logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    run()
