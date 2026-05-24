import os
from dotenv import load_dotenv

load_dotenv()

# ── Broker credentials ────────────────────────────────────────────────────────
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER      = os.getenv("ALPACA_PAPER", "true").lower() == "true"

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    raise EnvironmentError(
        "Missing ALPACA_API_KEY or ALPACA_SECRET_KEY. "
        "Copy .env.example → .env and fill in your keys."
    )

# ── Universe of symbols to trade ─────────────────────────────────────────────
SYMBOLS = ["AAPL", "MSFT", "TSLA", "SPY", "QQQ"]

# ── Risk parameters ───────────────────────────────────────────────────────────
MAX_POSITION_PCT   = 0.05   # max 5% of portfolio in any single position
STOP_LOSS_PCT      = 0.02   # exit if position drops 2%
DAILY_LOSS_LIMIT   = 0.03   # halt all trading if daily PnL < -3%
MAX_OPEN_POSITIONS = 5      # max concurrent positions

# ── Data settings ─────────────────────────────────────────────────────────────
BAR_TIMEFRAME      = "1Min"  # 1Min, 5Min, 15Min, 1Hour, 1Day
LOOKBACK_DAYS      = 30      # days of historical data to load on startup

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = "logs"
