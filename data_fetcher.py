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


def _has_nan(value) -> bool:
    """dict/list の中に float nan が含まれていれば True"""
    import math
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, dict):
        return any(_has_nan(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_nan(v) for v in value)
    return False


def _safe_float(value) -> float | None:
    """nan / inf を None に変換する安全な float 変換。JSON シリアライズ安全。"""
    import math
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _pct_change(current, base) -> float | None:
    """騰落率(%)を JSON safe に計算。算出不能なら None。"""
    if current is None or not base:
        return None
    v = _safe_float((current / base - 1) * 100)
    return None if v is None else round(v, 2)


def get_cached(key: str, max_age_hours: int = 12):
    """キャッシュからデータ取得（max_age_hours以内なら有効・nan含む値は無効）"""
    conn = get_db()
    row = conn.execute(
        "SELECT value, updated_at FROM cache WHERE key = ?", (key,)
    ).fetchone()
    conn.close()

    if row:
        updated = datetime.fromisoformat(row[1])
        if datetime.now() - updated < timedelta(hours=max_age_hours):
            data = json.loads(row[0])
            if _has_nan(data):
                return None  # nan を含むキャッシュは無効として再取得させる
            return data
    return None


def set_cache(key: str, value):
    """キャッシュにデータ保存（nan を含む値は保存しない）"""
    if _has_nan(value):
        return  # nan を含む結果はキャッシュしない（次回リクエストで再取得）
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
        import math
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        # NaN行を除去（yfinanceの破壊的変更対策）
        hist = hist.dropna(subset=["Close"])
        if len(hist) < ma_period:
            return {"value": None, "error": f"{ma_period}日分のデータ不足"}

        ma = hist["Close"].rolling(window=ma_period).mean()
        current_price = float(hist["Close"].iloc[-1])
        current_ma = float(ma.iloc[-1])

        # nan チェック（yfinanceが nan を返す場合の安全網）
        if math.isnan(current_price) or math.isnan(current_ma) or current_ma == 0:
            return {"value": None, "error": "yfinanceが NaN を返しました（データ取得失敗）"}

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
            hist = hist.dropna(subset=["Close"])
            current = d1 = None
            if len(hist) >= 2:
                current = _safe_float(hist["Close"].iloc[-1])
                d1 = _safe_float(hist["Close"].iloc[-2])
                w1 = _safe_float(hist["Close"].iloc[-6]) if len(hist) > 5 else d1
                m1 = _safe_float(hist["Close"].iloc[-22]) if len(hist) > 21 else d1

            # change_1d が数値にならない銘柄は error 扱いにする
            # （フロントは change_1d.toFixed() を呼ぶため None を渡せない）
            if current is None or not d1:
                sectors[name] = {"ticker": ticker, "error": "取得失敗"}
            else:
                sectors[name] = {
                    "ticker": ticker,
                    "price": round(current, 2),
                    "change_1d": _pct_change(current, d1),
                    "change_1w": _pct_change(current, w1),
                    "change_1m": _pct_change(current, m1),
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

    # WTI は CL=F 専用（USO は WTI 連動 ETF だが価格レベルが違うため絶対値での代用不可）
    # 2026-05-18: USO $148.23 が WTI として誤表示されたバグ修正。
    # CL=F 直接取得失敗時は fetch_daily_closes("CL=F") の日足終値にフォールバックする。
    tickers = {
        "wti": ["CL=F"],              # WTI は CL=F 専用
        "gold": ["GC=F", "GLD"],       # 金先物、フォールバック: GLD ETF
        "usdjpy": ["JPY=X", "USDJPY=X"],
    }
    result = {}
    for name, ticker_list in tickers.items():
        fetched = False
        for ticker in ticker_list:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="5d")
                hist = hist.dropna(subset=["Close"])
                if len(hist) >= 2:
                    current = _safe_float(hist["Close"].iloc[-1])
                    prev = _safe_float(hist["Close"].iloc[-2])
                    if current is None or prev is None or prev == 0:
                        time.sleep(1)
                        continue
                    result[name] = {
                        "value": round(current, 2),
                        "change_pct": round((current / prev - 1) * 100, 2),
                        "ticker_used": ticker,
                    }
                    fetched = True
                    break
                time.sleep(1)
            except Exception:
                time.sleep(1)
                continue
        if not fetched and name == "wti":
            # WTI 専用: CL=F 直接取得失敗時、日足終値キャッシュから取り直す
            daily = fetch_daily_closes("CL=F", days=2)
            if len(daily) >= 2:
                current = daily[-1]["close"]
                prev = daily[-2]["close"]
                result[name] = {
                    "value": current,
                    "change_pct": round((current / prev - 1) * 100, 2),
                    "ticker_used": "CL=F (daily_close fallback)",
                }
                fetched = True
        if not fetched:
            # 全ティッカー失敗 → 期限切れキャッシュからでも取る
            stale = get_cached(f"geopolitical_{name}_stale", max_age_hours=168)  # 1週間
            if stale:
                stale["stale"] = True
                result[name] = stale
            else:
                result[name] = {"value": None, "error": "取得失敗"}

    result["source"] = "yfinance"
    set_cache("geopolitical", result)
    # 個別にも長期キャッシュ保存（フォールバック用）
    for name in ["wti", "gold", "usdjpy"]:
        if name in result and result[name].get("value") is not None:
            set_cache(f"geopolitical_{name}_stale", result[name])
    return result


# ============================================================
# 監視銘柄（一発逆転枠）
# ============================================================
WATCHLIST = {
    "SPY": "S&P500 ETF",
    "SOXL": "半導体3倍レバ",
    "NVDA": "NVIDIA",
    "TQQQ": "ナスダック3倍レバ",
    "XLE": "エネルギーETF",
    "GLD": "ゴールドETF",
}


# ============================================================
# 日足終値履歴（ヒステリシス判定用）
# ============================================================
# 日中の瞬間値で判定するとシグナルが揺れるため、日足終値ベースで発動・解除を判定する。
# これにより清水さんが翌朝注文できるリードタイムを確保する。
DAILY_CLOSE_TICKERS = {
    "CL=F": "WTI原油",
    "SPY": "S&P500 ETF",
    "GLD": "ゴールドETF",
    "NVDA": "NVIDIA",
    "SOXL": "半導体3倍レバ",
    "XLE": "エネルギーETF",
    "GDX": "金鉱株ETF",
}


def fetch_daily_closes(ticker: str, days: int = 10) -> list:
    """直近N日分の日足終値を返す。最新が末尾。[{date, close}, ...]"""
    cache_key = f"daily_closes:{ticker}:{days}"
    cached = get_cached(cache_key, max_age_hours=4)
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker)
        # 余裕を持って倍の期間で取得（休場日を考慮）
        hist = stock.history(period=f"{max(days * 2, 20)}d", interval="1d")
        if hist.empty:
            return []
        hist = hist.dropna(subset=["Close"])
        closes = []
        for idx, row in hist.tail(days).iterrows():
            close_val = _safe_float(row["Close"])
            if close_val is not None:
                closes.append({
                    "date": idx.date().isoformat(),
                    "close": round(close_val, 2),
                })
        set_cache(cache_key, closes)
        return closes
    except Exception:
        return []


def fetch_all_daily_closes(days: int = 10) -> dict:
    """ヒステリシス判定に必要な全銘柄の日足終値履歴をまとめて返す"""
    cache_key = f"all_daily_closes:{days}"
    cached = get_cached(cache_key, max_age_hours=4)
    if cached:
        return cached

    result = {}
    for ticker in DAILY_CLOSE_TICKERS.keys():
        closes = fetch_daily_closes(ticker, days)
        if closes:
            result[ticker] = closes
        time.sleep(0.5)
    set_cache(cache_key, result)
    return result


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
            hist = hist.dropna(subset=["Close"])
            if not hist.empty:
                current = _safe_float(hist["Close"].iloc[-1])
                high_52w = _safe_float(hist["Close"].max())
                if current is None or high_52w is None or high_52w == 0:
                    result[ticker] = {"label": label, "error": "NaN値を受信"}
                else:
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
