"""
Crash Detector API - FastAPI Server
暴落検知・投資タイミング判断システム
"""

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from data_fetcher import (
    fetch_vix,
    fetch_fear_greed,
    fetch_rsi,
    fetch_credit_spread,
    fetch_yield_curve,
    fetch_ma_deviation,
    fetch_sector_heatmap,
    fetch_geopolitical,
    fetch_watchlist,
)
from crash_score import calculate_crash_score

load_dotenv()

app = FastAPI(
    title="Crash Detector API",
    description="暴落検知・投資タイミング判断システム",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRED_API_KEY = os.getenv("FRED_API_KEY")

# 静的ファイル配信（フロントエンド統合）
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    """ダッシュボードHTMLを返す（staticフォルダがあれば）"""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {
        "name": "Crash Detector API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/score")
def get_crash_score():
    """
    メインエンドポイント: Crash Score + 全指標を返す
    """
    # 各指標を取得
    vix = fetch_vix(FRED_API_KEY)
    fear_greed = fetch_fear_greed()
    rsi = fetch_rsi("SPY")
    credit_spread = fetch_credit_spread(FRED_API_KEY)
    yield_curve = fetch_yield_curve(FRED_API_KEY)
    ma_deviation = fetch_ma_deviation("SPY")

    # 統合スコア算出
    indicators = {
        "vix": vix,
        "fear_greed": fear_greed,
        "rsi": rsi,
        "credit_spread": credit_spread,
        "pcr": {"value": None},  # 将来実装
        "aaii_bear": {"value": None},  # 将来実装
        "ma_deviation": ma_deviation,
        "yield_curve": yield_curve,
    }

    score = calculate_crash_score(indicators)

    return {
        "crash_score": score,
        "indicators": indicators,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/indicators")
def get_all_indicators():
    """全指標の生データを返す"""
    return {
        "vix": fetch_vix(FRED_API_KEY),
        "fear_greed": fetch_fear_greed(),
        "rsi": fetch_rsi("SPY"),
        "credit_spread": fetch_credit_spread(FRED_API_KEY),
        "yield_curve": fetch_yield_curve(FRED_API_KEY),
        "ma_deviation": fetch_ma_deviation("SPY"),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/sectors")
def get_sectors():
    """セクターヒートマップ"""
    return fetch_sector_heatmap()


@app.get("/api/geopolitical")
def get_geopolitical():
    """地政学リスク指標（原油・金・ドル円）"""
    return fetch_geopolitical()


@app.get("/api/watchlist")
def get_watchlist():
    """監視銘柄（SOXL, NVIDIA等）"""
    return fetch_watchlist()


@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
