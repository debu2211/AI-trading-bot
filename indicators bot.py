"""
data/indicators.py — Technical indicators for strategy use.

All functions take a DataFrame (from DataFeed) and return a Series
or DataFrame. No external TA library required — pure pandas/numpy.

Add custom indicators here as you build out your strategy.
"""

import numpy as np
import pandas as pd


# ── Trend indicators ──────────────────────────────────────────────────────────

def ema(df: pd.DataFrame, period: int, col: str = "close") -> pd.Series:
    """Exponential Moving Average."""
    return df[col].ewm(span=period, adjust=False).mean()


def sma(df: pd.DataFrame, period: int, col: str = "close") -> pd.Series:
    """Simple Moving Average."""
    return df[col].rolling(window=period).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    """
    Volume Weighted Average Price.
    Resets daily — use on intraday (1Min/5Min) data.
    """
    if "vwap" in df.columns and df["vwap"].notna().any():
        return df["vwap"]
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return (typical * df["volume"]).cumsum() / df["volume"].cumsum()


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD — Moving Average Convergence Divergence.

    Returns DataFrame with columns: macd, signal, histogram
    """
    fast_ema  = df["close"].ewm(span=fast,   adjust=False).mean()
    slow_ema  = df["close"].ewm(span=slow,   adjust=False).mean()
    macd_line = fast_ema - slow_ema
    sig_line  = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({
        "macd":      macd_line,
        "signal":    sig_line,
        "histogram": macd_line - sig_line,
    }, index=df.index)


def bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
) -> pd.DataFrame:
    """
    Bollinger Bands.

    Returns DataFrame with columns: upper, middle, lower, width, pct_b
    """
    mid   = df["close"].rolling(window=period).mean()
    std   = df["close"].rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    width = (upper - lower) / mid
    pct_b = (df["close"] - lower) / (upper - lower)
    return pd.DataFrame({
        "upper":  upper,
        "middle": mid,
        "lower":  lower,
        "width":  width,
        "pct_b":  pct_b,
    }, index=df.index)


# ── Momentum indicators ───────────────────────────────────────────────────────

def rsi(df: pd.DataFrame, period: int = 14, col: str = "close") -> pd.Series:
    """
    Relative Strength Index (0–100).
    Oversold < 30, Overbought > 70.
    """
    delta  = df[col].diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    avg_g  = gain.ewm(com=period - 1, adjust=False).mean()
    avg_l  = loss.ewm(com=period - 1, adjust=False).mean()
    rs     = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stochastic(
    df: pd.DataFrame,
    k_period: int = 14,
    d_period: int = 3,
) -> pd.DataFrame:
    """
    Stochastic Oscillator (%K and %D).

    Returns DataFrame with columns: pct_k, pct_d
    """
    low_min  = df["low"].rolling(window=k_period).min()
    high_max = df["high"].rolling(window=k_period).max()
    pct_k = 100 * (df["close"] - low_min) / (high_max - low_min)
    pct_d = pct_k.rolling(window=d_period).mean()
    return pd.DataFrame({"pct_k": pct_k, "pct_d": pct_d}, index=df.index)


# ── Volatility indicators ─────────────────────────────────────────────────────

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range — measures volatility.
    Use for dynamic stop-loss sizing: stop = price - 2 * ATR
    """
    high_low   = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close  = (df["low"]  - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.ewm(com=period - 1, adjust=False).mean()


# ── Volume indicators ─────────────────────────────────────────────────────────

def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume — cumulative volume direction."""
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Volume Simple Moving Average — for unusual volume detection."""
    return df["volume"].rolling(window=period).mean()


# ── Signal helpers ────────────────────────────────────────────────────────────

def crossover(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """
    Returns True on bars where series_a crosses ABOVE series_b.

    Example (EMA crossover buy signal):
        signal = crossover(ema(df, 9), ema(df, 21))
    """
    above_now  = series_a > series_b
    above_prev = series_a.shift(1) > series_b.shift(1)
    return above_now & ~above_prev


def crossunder(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """
    Returns True on bars where series_a crosses BELOW series_b.

    Example (EMA crossover sell signal):
        signal = crossunder(ema(df, 9), ema(df, 21))
    """
    below_now  = series_a < series_b
    below_prev = series_a.shift(1) < series_b.shift(1)
    return below_now & ~below_prev
