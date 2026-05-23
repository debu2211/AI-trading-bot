"""
test_data_feed.py — Test and demo for the data pipeline.

Run this after test_connection.py passes to verify:
  1. Historical bar fetching works
  2. DataFeed cache and summary work
  3. All indicators compute correctly on real data
  4. Real-time streaming connects (press Ctrl+C to stop)

Usage:
    python test_data_feed.py
    python test_data_feed.py --stream    # also test live stream
"""

import sys
import asyncio
import argparse
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from broker import AlpacaClient
from data.feed import DataFeed
from data import indicators as ind

SYMBOLS = ["AAPL", "MSFT", "TSLA"]

def separator(title=""):
    w = 55
    if title:
        pad = (w - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("─" * w)


def test_historical(feed: DataFeed):
    separator("Historical bars")

    data = feed.get_history(SYMBOLS, days=30, timeframe="1Day")

    for symbol, df in data.items():
        if df.empty:
            print(f"  {symbol}: no data")
            continue

        latest = df.iloc[-1]
        prev   = df.iloc[-2] if len(df) > 1 else latest
        change = ((latest["close"] - prev["close"]) / prev["close"]) * 100
        sign   = "+" if change >= 0 else ""
        print(
            f"  {symbol:<6}  "
            f"close=${latest['close']:>8.2f}  "
            f"vol={int(latest['volume']):>10,}  "
            f"1d={sign}{change:.2f}%"
        )

    feed.summary()
    return data


def test_indicators(feed: DataFeed, data: dict):
    separator("Indicators")

    df = data.get("AAPL")
    if df is None or df.empty:
        print("  No AAPL data to test indicators on")
        return

    # Trend
    ema9  = ind.ema(df, 9)
    ema21 = ind.ema(df, 21)
    sma50 = ind.sma(df, 50) if len(df) >= 50 else None

    # Momentum
    rsi14 = ind.rsi(df, 14)
    macd_df = ind.macd(df)

    # Volatility
    atr14 = ind.atr(df, 14)
    bb    = ind.bollinger_bands(df, 20)

    # Signals
    buy_signal  = ind.crossover(ema9, ema21)
    sell_signal = ind.crossunder(ema9, ema21)

    last = df.index[-1]
    close = df["close"].iloc[-1]

    print(f"\n  AAPL as of {str(last)[:10]}")
    print(f"  Close       : ${close:.2f}")
    print(f"  EMA(9)      : ${ema9.iloc[-1]:.2f}")
    print(f"  EMA(21)     : ${ema21.iloc[-1]:.2f}")
    if sma50 is not None:
        print(f"  SMA(50)     : ${sma50.iloc[-1]:.2f}")
    print(f"  RSI(14)     : {rsi14.iloc[-1]:.1f}  "
          f"({'oversold' if rsi14.iloc[-1] < 30 else 'overbought' if rsi14.iloc[-1] > 70 else 'neutral'})")
    print(f"  MACD        : {macd_df['macd'].iloc[-1]:.3f}  "
          f"signal={macd_df['signal'].iloc[-1]:.3f}  "
          f"hist={macd_df['histogram'].iloc[-1]:.3f}")
    print(f"  ATR(14)     : ${atr14.iloc[-1]:.2f}  "
          f"(suggested stop: ${close - 2 * atr14.iloc[-1]:.2f})")
    print(f"  BB upper    : ${bb['upper'].iloc[-1]:.2f}  "
          f"lower=${bb['lower'].iloc[-1]:.2f}  "
          f"%B={bb['pct_b'].iloc[-1]:.2f}")

    # Recent crossover signals
    recent_buys  = buy_signal[buy_signal].tail(3)
    recent_sells = sell_signal[sell_signal].tail(3)
    if not recent_buys.empty:
        print(f"\n  Recent EMA(9/21) BUY signals:")
        for ts in recent_buys.index:
            print(f"    → {str(ts)[:10]}")
    if not recent_sells.empty:
        print(f"  Recent EMA(9/21) SELL signals:")
        for ts in recent_sells.index:
            print(f"    → {str(ts)[:10]}")

    print(f"\n  [OK] All indicators computed successfully")


async def test_stream(feed: DataFeed):
    separator("Real-time stream (Ctrl+C to stop)")
    print("  Connecting to Alpaca WebSocket...")

    bar_count = 0

    async def on_bar(symbol, df):
        nonlocal bar_count
        bar_count += 1
        row = df.iloc[-1]
        ts  = str(df.index[-1])[:19]
        print(
            f"  [{bar_count:>3}] {ts}  {symbol:<6}  "
            f"O={row['open']:.2f}  H={row['high']:.2f}  "
            f"L={row['low']:.2f}  C={row['close']:.2f}  "
            f"V={int(row['volume']):,}"
        )

    try:
        await feed.stream(SYMBOLS, on_bar=on_bar)
    except KeyboardInterrupt:
        feed.stop_stream()
        print(f"\n  Stream stopped. Received {bar_count} bars.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stream", action="store_true",
                        help="Also test live WebSocket streaming")
    args = parser.parse_args()

    separator("Data feed test")
    print(f"  Symbols   : {SYMBOLS}")
    print(f"  Started   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialise
    client = AlpacaClient()
    feed   = DataFeed(client)

    # 1. Historical data
    data = test_historical(feed)

    # 2. Indicators
    test_indicators(feed, data)

    # 3. Streaming (optional)
    if args.stream:
        if not client.is_market_open():
            print("\n  [WARN] Market is closed — stream will connect but "
                  "no bars will arrive until market opens.")
        asyncio.run(test_stream(feed))

    separator()
    print("  Phase 2 complete. Data pipeline is ready.")
    separator()


if __name__ == "__main__":
    main()
