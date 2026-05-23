import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

import pandas as pd
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar

import config

logger = logging.getLogger(__name__)

# Timeframe aliases — pass these as strings in config.py
TIMEFRAMES = {
    "1Min":  TimeFrame(1,  TimeFrameUnit.Minute),
    "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1,  TimeFrameUnit.Hour),
    "1Day":  TimeFrame(1,  TimeFrameUnit.Day),
}


class DataFeed:
    """
    Wraps AlpacaClient to provide clean DataFrames for both
    historical bars and real-time streaming bars.
    """

    def __init__(self, client):
        """
        Args:
            client: An initialised AlpacaClient instance.
        """
        self._client = client
        self._stream: Optional[StockDataStream] = None
        # In-memory bar cache: symbol → DataFrame
        self._cache: Dict[str, pd.DataFrame] = {}

    # ── Historical data ───────────────────────────────────────────────────────

    def get_history(
        self,
        symbols: list[str] | str,
        days: int = config.LOOKBACK_DAYS,
        timeframe: str = config.BAR_TIMEFRAME,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical OHLCV bars for one or more symbols.

        Returns:
            Dict of {symbol: DataFrame} with columns:
            open, high, low, close, volume, vwap, trade_count

        Example:
            feed = DataFeed(client)
            data = feed.get_history(["AAPL", "TSLA"], days=30)
            df = data["AAPL"]
            print(df.tail())
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        tf = TIMEFRAMES.get(timeframe)
        if tf is None:
            raise ValueError(
                f"Unknown timeframe '{timeframe}'. "
                f"Choose from: {list(TIMEFRAMES.keys())}"
            )

        start = datetime.now(timezone.utc) - timedelta(days=days)

        logger.info(
            f"Fetching {timeframe} bars for {symbols} "
            f"(last {days} days)"
        )

        try:
            bars = self._client.get_bars(
                symbols=symbols,
                timeframe=tf,
                start=start,
            )
            raw_df = bars.df
        except Exception as e:
            logger.error(f"Historical data fetch failed: {e}")
            raise

        result = {}
        for symbol in symbols:
            try:
                # Multi-symbol response has a MultiIndex (symbol, timestamp)
                if isinstance(raw_df.index, pd.MultiIndex):
                    df = raw_df.xs(symbol, level="symbol").copy()
                else:
                    df = raw_df.copy()

                df = self._clean_df(df)
                self._cache[symbol] = df
                result[symbol] = df
                logger.info(f"  {symbol}: {len(df)} bars loaded")
            except KeyError:
                logger.warning(f"  {symbol}: no data returned")

        return result

    def get_latest_bars(
        self,
        symbol: str,
        n: int = 50,
        timeframe: str = config.BAR_TIMEFRAME,
    ) -> pd.DataFrame:
        """
        Get the last N bars for a symbol (from cache or fresh fetch).
        Use this inside the strategy to get the data window it needs.

        Example:
            df = feed.get_latest_bars("AAPL", n=20)
            ema = df["close"].ewm(span=20).mean()
        """
        if symbol not in self._cache:
            data = self.get_history([symbol], timeframe=timeframe)
            return data.get(symbol, pd.DataFrame()).tail(n)
        return self._cache[symbol].tail(n)

    def refresh(
        self,
        symbols: list[str],
        timeframe: str = config.BAR_TIMEFRAME,
    ):
        """Re-fetch and update cache for given symbols."""
        self.get_history(symbols, timeframe=timeframe)

    # ── Real-time streaming ───────────────────────────────────────────────────

    async def stream(
        self,
        symbols: list[str],
        on_bar: Callable[[str, pd.DataFrame], None],
        timeframe: str = config.BAR_TIMEFRAME,
    ):
        """
        Subscribe to real-time bar updates via WebSocket.
        Calls `on_bar(symbol, df)` every time a bar closes.

        Args:
            symbols:   List of ticker symbols to watch.
            on_bar:    Async callback — receives (symbol, latest_df).
            timeframe: Bar interval (default from config).

        Example:
            async def handle_bar(symbol, df):
                print(f"{symbol} close: {df['close'].iloc[-1]:.2f}")

            await feed.stream(["AAPL", "TSLA"], on_bar=handle_bar)
        """
        self._stream = self._client.get_stream()

        async def _bar_handler(bar: Bar):
            symbol = bar.symbol
            new_row = pd.DataFrame([{
                "open":        float(bar.open),
                "high":        float(bar.high),
                "low":         float(bar.low),
                "close":       float(bar.close),
                "volume":      int(bar.volume),
                "vwap":        float(bar.vwap) if bar.vwap else None,
                "trade_count": int(bar.trade_count) if bar.trade_count else None,
            }], index=pd.DatetimeIndex([bar.timestamp]))

            # Append to cache and trim to last 500 bars
            if symbol in self._cache:
                self._cache[symbol] = pd.concat(
                    [self._cache[symbol], new_row]
                ).tail(500)
            else:
                self._cache[symbol] = new_row

            logger.debug(
                f"Bar: {symbol} | "
                f"O={bar.open:.2f} H={bar.high:.2f} "
                f"L={bar.low:.2f} C={bar.close:.2f} "
                f"V={bar.volume:,}"
            )

            await on_bar(symbol, self._cache[symbol])

        # Subscribe to bar updates for each symbol
        for symbol in symbols:
            self._stream.subscribe_bars(_bar_handler, symbol)

        logger.info(f"Streaming {timeframe} bars for: {symbols}")
        self._stream.run()

    def stop_stream(self):
        """Gracefully stop the WebSocket stream."""
        if self._stream:
            self._stream.stop()
            logger.info("Stream stopped")

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalise column names and index, drop nulls."""
        df.index = pd.to_datetime(df.index, utc=True)
        df.index.name = "timestamp"
        df = df[["open", "high", "low", "close", "volume", "vwap", "trade_count"]]
        df = df.dropna(subset=["close"])
        df = df.sort_index()
        return df

    def get_cached_symbols(self) -> list[str]:
        return list(self._cache.keys())

    def summary(self):
        """Print a quick summary of what's in cache."""
        if not self._cache:
            print("Cache is empty — call get_history() first.")
            return
        print(f"\n{'Symbol':<8} {'Bars':>6}  {'From':<22} {'To'}")
        print("-" * 60)
        for sym, df in self._cache.items():
            if df.empty:
                continue
            print(
                f"{sym:<8} {len(df):>6}  "
                f"{str(df.index[0])[:19]:<22} "
                f"{str(df.index[-1])[:19]}"
            )
        print()
