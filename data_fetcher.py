"""
Crash Detector - Data Fetcher
各種APIからマーケットデータを取得する
"""

import time
import json
import sqlite3
import os
import certifi
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Windows日本語パスでのSSL証明書エラー回避
# certifiのパスに日本語が含まれるとcurl_cffiが読めないため、TEMPにコピー
_cert_src = certifi.where()
_cert_dst = os.path.join(os.environ.get("TEMP", "/tmp"), "cacert.pem")
try:
    shutil.copy2(_cert_src, _cert_dst)
    os.environ["CURL_CA_BUNDLE"] = _cert_dst
    os.environ["SSL_CERT_FILE"] = _cert_dst
    os.environ["REQUESTS_CA_BUNDLE"] = _cert_dst
except Exception:
    os.environ["CURL_CA_BUNDLE"] = _cert_src
    os.environ["SSL_CERT_FILE"] = _cert_src
    os.environ["REQUESTS_CA_BUNDLE"] = _cert_src

import yfinance as yf
import pandas as pd
import requests

DB_PATH = Path(__file__).parent / "cache.db"


def get_db():
    """SQLiteキャッシュDB接続"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)
    return conn


def get_cached(key: str, max_age_hours: int = 12):
    """キャッシュからデータ取得（max_age_hours以内なら有効）"""
    conn = get_db()
    row = conn.execute(
        "SELECT value, updated_at FROM cache WHERE key = ?", (key,)
    ).fetchone()
    conn.close()

    if row:
        updated = datetime.fromisoformat(row[1])
        if datetime.now() - updated < timedelta(hours=max_age_hours):
            return json.loads(row[0])
    return None


def set_cache(key: str, value):
    """キャッシュにデータ保存"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, value, updated_at) VALUES (?, ?, ?)",
        (key, json.dumps(value), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ============================================================
# VIX（FRED API）
# ============================================================
def fetch_vix(fred_api_key: str = None) -> dict:
    """VIX（恐怖指数）を取得"""
    cached = get_cached("vix")
    if cached:
        return cached

    # まずyfinanceで試す（APIキー不要）
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="5d")
        if not hist.empty:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
            result = {
                "value": round(current, 2),
                "prev": round(prev, 2),
                "change": round(current - prev, 2),
                "source": "yfinance",
            }
            set_cache("vix", result)
            return result
    except Exception:
        pass

    # フォールバック: FRED API
    if fred_api_key:
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": "VIXCLS",
                "api_key": fred_api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            obs = [o for o in data["observations"] if o["value"] != "."]
            if obs:
                current = float(obs[0]["value"])
                prev = float(obs[1]["value"]) if len(obs) > 1 else current
                result = {
                    "value": round(current, 2),
                    "prev": round(prev, 2),
                    "change": round(current - prev, 2),
                    "source": "FRED",
                }
                set_cache("vix", result)
                return result
        except Exception:
            pass

    return {"value": None, "error": "VIX取得失敗"}


# ============================================================
# CNN Fear & Greed Index
# ============================================================
def fetch_fear_greed() -> dict:
    """CNN Fear & Greed Indexを取得"""
    cached = get_cached("fear_greed")
    if cached:
        return cached

    # Method 1: CNN API (日付なしURL)
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        })
        if resp.status_code == 200:
            data = resp.json()
            fg = data.get("fear_and_greed", {})
            result = {
                "value": round(fg.get("score", 0), 1),
                "rating": fg.get("rating", "unknown"),
                "prev_close": round(fg.get("previous_close", 0), 1),
                "source": "CNN",
            }
            set_cache("fear_greed", result)
            return result
    except Exception:
        pass

    # Method 2: Alternative Fear & Greed API
    try:
        url = "https://fear-and-greed-index.p.rapidapi.com/v1/fgi"
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        if resp.status_code == 200:
            data = resp.json()
            result = {
                "value": round(float(data.get("fgi", {}).get("now", {}).get("value", 50)), 1),
                "rating": data.get("fgi", {}).get("now", {}).get("valueText", "unknown"),
                "source": "alternative",
            }
            set_cache("fear_greed", result)
            return result
    except Exception:
        pass

    return {"value": None, "error": "Fear&Greed取得失敗: Bot検知またはAPI変更"}


# ============================================================
# RSI（yfinance + pandas-ta）
# ============================================================
def fetch_rsi(ticker: str = "SPY", period: int = 14) -> dict:
    """RSI（相対力指数）を計算"""
    cached = get_cached(f"rsi_{ticker}")
    if cached:
        return cached

    try:
        from ta.momentum import RSIIndicator

        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo")
        if hist.empty:
            return {"value": None, "error": f"{ticker}データ取得失敗"}

        rsi_indicator = RSIIndicator(hist["Close"], window=period)
        rsi = rsi_indicator.rsi()
        current_rsi = float(rsi.iloc[-1])
        prev_rsi = float(rsi.iloc[-2])

        result = {
            "value": round(current_rsi, 1),
            "prev": round(prev_rsi, 1),
            "ticker": ticker,
            "source": "yfinance+pandas-ta",
        }
        set_cache(f"rsi_{ticker}", result)
        return result
    except Exception as e:
        return {"value": None, "error": f"RSI計算失敗: {str(e)}"}


# ============================================================
# クレジットスプレッド（FRED API）
# ============================================================
def fetch_credit_spread(fred_api_key: str = None) -> dict:
    """ハイイールドスプレッドを取得"""
    cached = get_cached("credit_spread")
    if cached:
        return cached

    if not fred_api_key:
        return {"value": None, "error": "FRED APIキーが未設定"}

    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "BAMLH0A0HYM2",
            "api_key": fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 5,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        obs = [o for o in data["observations"] if o["value"] != "."]
        if obs:
            current = float(obs[0]["value"])
            prev = float(obs[1]["value"]) if len(obs) > 1 else current
            result = {
                "value": round(current * 100, 0),  # %→bps変換
                "prev": round(prev * 100, 0),
                "source": "FRED",
            }
            set_cache("credit_spread", result)
            return result
    except Exception as e:
        return {"value": None, "error": f"クレジットスプレッド取得失敗: {str(e)}"}

    return {"value": None, "error": "データなし"}


# ============================================================
# イールドカーブ（FRED API）
# ============================================================
def fetch_yield_curve(fred_api_key: str = None) -> dict:
    """10年-2年国債利回り差を取得"""
    cached = get_cached("yield_curve")
    if cached:
        return cached

    if not fred_api_key:
        return {"value": None, "error": "FRED APIキーが未設定"}

    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        results = {}
        for series_id in ["DGS10", "DGS2"]:
            params = {
                "series_id": series_id,
                "api_key": fred_api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            obs = [o for o in data["observations"] if o["value"] != "."]
            if obs:
                results[series_id] = float(obs[0]["value"])
            time.sleep(1)

        if "DGS10" in results and "DGS2" in results:
            spread = results["DGS10"] - results["DGS2"]
            result = {
                "value": round(spread, 3),
                "y10": results["DGS10"],
                "y2": results["DGS2"],
                "inverted": spread < 0,
                "source": "FRED",
            }
            set_cache("yield_curve", result)
            return result
    except Exception as e:
        return {"value": None, "error": f"イールドカーブ取得失敗: {str(e)}"}

    return {"value": None, "error": "データなし"}


# ============================================================
# 移動平均乖離率
# ============================================================
def fetch_ma_deviation(ticker: str = "SPY", ma_period: int = 200) -> dict:
    """200日移動平均からの乖離率を計算"""
    cached = get_cached(f"ma_dev_{ticker}")
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if len(hist) < ma_period:
            return {"value": None, "error": f"{ma_period}日分のデータ不足"}

        ma = hist["Close"].rolling(window=ma_period).mean()
        current_price = float(hist["Close"].iloc[-1])
        current_ma = float(ma.iloc[-1])
        deviation = ((current_price - current_ma) / current_ma) * 100

        result = {
            "value": round(deviation, 2),
            "price": round(current_price, 2),
            "ma": round(current_ma, 2),
            "ticker": ticker,
            "source": "yfinance",
        }
        set_cache(f"ma_dev_{ticker}", result)
        return result
    except Exception as e:
        return {"value": None, "error": f"MA乖離率計算失敗: {str(e)}"}


# ============================================================
# セクターヒートマップ
# ============================================================
SECTOR_ETFS = {
    "Energy": "XLE",
    "Utilities": "XLU",
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "RealEstate": "XLRE",
    "ConsumerDisc": "XLY",
    "Materials": "XLB",
    "Communication": "XLC",
    "Industrials": "XLI",
    "ConsumerStap": "XLP",
}


def fetch_sector_heatmap() -> dict:
    """セクター別騰落率を取得"""
    cached = get_cached("sector_heatmap", max_age_hours=6)
    if cached:
        return cached

    sectors = {}
    for name, ticker in SECTOR_ETFS.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="3mo")
            if len(hist) >= 2:
                current = float(hist["Close"].iloc[-1])
                d1 = float(hist["Close"].iloc[-2])
                w1 = float(hist["Close"].iloc[-6]) if len(hist) > 5 else d1
                m1 = float(hist["Close"].iloc[-22]) if len(hist) > 21 else d1

                sectors[name] = {
                    "ticker": ticker,
                    "price": round(current, 2),
                    "change_1d": round((current / d1 - 1) * 100, 2),
                    "change_1w": round((current / w1 - 1) * 100, 2),
                    "change_1m": round((current / m1 - 1) * 100, 2),
                }
            time.sleep(1)  # レート制限対策
        except Exception:
            sectors[name] = {"ticker": ticker, "error": "取得失敗"}

    result = {"sectors": sectors, "source": "yfinance"}
    set_cache("sector_heatmap", result)
    return result


# ============================================================
# 地政学リスク指標
# ============================================================
def fetch_geopolitical() -> dict:
    """原油・金・ドル円を取得"""
    cached = get_cached("geopolitical", max_age_hours=6)
    if cached:
        return cached

    tickers = {
        "wti": "CL=F",
        "gold": "GC=F",
        "usdjpy": "JPY=X",
    }
    result = {}
    for name, ticker in tickers.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if len(hist) >= 2:
                current = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                result[name] = {
                    "value": round(current, 2),
                    "change_pct": round((current / prev - 1) * 100, 2),
                }
            time.sleep(1)
        except Exception:
            result[name] = {"value": None, "error": "取得失敗"}

    result["source"] = "yfinance"
    set_cache("geopolitical", result)
    return result


# ============================================================
# 監視銘柄（一発逆転枠）
# ============================================================
WATCHLIST = {
    "SOXL": "半導体3倍レバ",
    "NVDA": "NVIDIA",
    "TQQQ": "ナスダック3倍レバ",
    "XLE": "エネルギーETF",
}


def fetch_watchlist() -> dict:
    """監視銘柄の現在値と高値からの下落率"""
    cached = get_cached("watchlist", max_age_hours=6)
    if cached:
        return cached

    result = {}
    for ticker, label in WATCHLIST.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if not hist.empty:
                current = float(hist["Close"].iloc[-1])
                high_52w = float(hist["Close"].max())
                drawdown = ((current - high_52w) / high_52w) * 100

                result[ticker] = {
                    "label": label,
                    "price": round(current, 2),
                    "high_52w": round(high_52w, 2),
                    "drawdown_pct": round(drawdown, 1),
                }
            time.sleep(1)
        except Exception:
            result[ticker] = {"label": label, "error": "取得失敗"}

    set_cache("watchlist", result)
    return result
