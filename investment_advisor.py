"""
Investment Advisor Engine
セクター別の買い/待ちシグナルを判定し、具体的なアクション指示を生成する

清水さんの投資戦略（docs/investment-strategy-2026Q2.md）をコード化したもの
"""

from datetime import datetime


# ============================================================
# 戦略パラメータ（ダッシュボード上で表示・将来的に編集可能にする）
# ============================================================
STRATEGY = {
    "total_budget": 2970000,  # 297万
    "nisa_budget": 2400000,   # 240万
    "tokutei_budget": 570000, # 57万
    "tranches": [
        {"label": "1回目", "amount": 600000, "status": "pending"},
        {"label": "2回目", "amount": 600000, "status": "pending"},
        {"label": "3回目", "amount": 600000, "status": "pending"},
        {"label": "4回目", "amount": 600000, "status": "pending"},
    ],
}


# ============================================================
# セクター別シグナル判定
# ============================================================

def evaluate_energy(wti_price: float, xle_price: float, xle_high_52w: float) -> dict:
    """
    エネルギーセクターの買い/待ちシグナルを判定

    清水さんの読み: エネルギーは伸びる（ホルムズ海峡リスク、AI電力需要）
    教訓: 3月に買えなかった。セクター個別のシグナルが必要だった
    """
    if wti_price is None or xle_price is None:
        return _unknown("エネルギー", "データ取得失敗")

    xle_from_high = ((xle_price - xle_high_52w) / xle_high_52w) * 100 if xle_high_52w else 0

    # 判定ロジック
    if wti_price <= 80:
        signal = "BUY"
        action = f"NISA枠でXLE（エネルギーETF）を60万買い。WTI ${wti_price}は停戦後の底値圏"
        urgency = "high"
        reason = "原油が大幅下落。停戦合意後のバーゲン価格"
    elif wti_price <= 90:
        signal = "BUY"
        action = f"NISA枠でXLE 60万を検討。WTI ${wti_price}は調整後の買い場"
        urgency = "medium"
        reason = "原油調整中。エネルギー長期上昇トレンドへの押し目"
    elif xle_from_high <= -20:
        signal = "BUY"
        action = f"XLEが52週高値から{xle_from_high:.0f}%下落。反発を狙って買い"
        urgency = "medium"
        reason = "ETF自体が大幅下落。原油価格に関わらず買い場"
    elif wti_price >= 120:
        signal = "CONSIDER"
        action = f"特定口座でXOM/CVXを30万検討。WTI ${wti_price}で封鎖長期化確認"
        urgency = "low"
        reason = "原油高が続くなら個別株で利益を取る。ただし天井リスクあり"
    elif wti_price >= 100 and xle_from_high >= -10:
        signal = "WAIT"
        action = "エネルギーは待機。XLE高値圏（停戦で急落リスク）"
        urgency = "none"
        reason = f"XLE 52週高値の{100 + xle_from_high:.0f}%水準。上昇余地より下落リスクが大きい"
    else:
        signal = "WATCH"
        action = "エネルギーは監視継続。WTI $90以下で買い検討"
        urgency = "none"
        reason = "中間価格帯。明確なシグナルなし"

    return {
        "sector": "エネルギー",
        "signal": signal,
        "action": action,
        "urgency": urgency,
        "reason": reason,
        "data": {
            "wti": wti_price,
            "xle_price": xle_price,
            "xle_high_52w": xle_high_52w,
            "xle_from_high_pct": round(xle_from_high, 1),
        },
        "buy_targets": {
            "best": f"WTI ${80}以下（停戦合意時）",
            "good": f"WTI ${90}以下（調整時）",
            "current": f"WTI ${wti_price}",
        },
    }


def evaluate_semiconductor(
    nvda_price: float, nvda_high_52w: float,
    soxl_price: float, crash_score: float
) -> dict:
    """
    半導体セクターの買い/待ちシグナルを判定

    NVIDIA: AI需要の王者。ファンダメンタルズは過去最高
    SOXL: 半導体3倍レバ。底値での一発逆転枠
    """
    if nvda_price is None:
        return _unknown("半導体", "NVIDIAデータ取得失敗")

    nvda_from_high = ((nvda_price - nvda_high_52w) / nvda_high_52w) * 100 if nvda_high_52w else 0

    if nvda_from_high <= -40:
        signal = "STRONG_BUY"
        action = f"NVIDIA ${nvda_price}（高値比{nvda_from_high:.0f}%）。特定口座で25万即買い"
        urgency = "high"
        reason = "過去最高決算のNVIDIAが-40%は異常値。AI需要は健在"
    elif nvda_from_high <= -30:
        signal = "BUY"
        action = f"NVIDIA ${nvda_price}（高値比{nvda_from_high:.0f}%）。特定口座で25万買い"
        urgency = "high"
        reason = "バリュエーション調整による下落。業績は過去最高"
    elif nvda_from_high <= -20:
        signal = "CONSIDER"
        action = f"NVIDIA ${nvda_price}（高値比{nvda_from_high:.0f}%）。10万の打診買いを検討"
        urgency = "medium"
        reason = "買い圏に近づいている。決算（5/20）前の打診買い候補"
    elif nvda_from_high <= -10:
        signal = "WATCH"
        action = f"NVIDIAは監視継続。高値比{nvda_from_high:.0f}%でまだ割高"
        urgency = "none"
        reason = "もう少し下がればチャンス"
    else:
        signal = "WAIT"
        action = "NVIDIAは待機。高値圏で割高"
        urgency = "none"
        reason = f"高値比{nvda_from_high:.0f}%。下落を待つ"

    # SOXL判定（Crash Scoreと連動）
    soxl_advice = None
    if soxl_price is not None and soxl_price <= 30 and crash_score is not None and crash_score <= 20:
        soxl_advice = {
            "signal": "BUY",
            "action": f"SOXL ${soxl_price} + Crash Score {crash_score}。特定口座で25万買い",
            "reason": "半導体3倍ETFが暴落 + 市場全体が恐怖の極み。一発逆転のチャンス",
        }
    elif soxl_price is not None and soxl_price <= 20:
        soxl_advice = {
            "signal": "STRONG_BUY",
            "action": f"SOXL ${soxl_price}。底値圏。特定口座で25万買い",
            "reason": "コロナショック級の下落。ここで買えれば10倍の可能性",
        }

    return {
        "sector": "半導体",
        "signal": signal,
        "action": action,
        "urgency": urgency,
        "reason": reason,
        "data": {
            "nvda_price": nvda_price,
            "nvda_high_52w": nvda_high_52w,
            "nvda_from_high_pct": round(nvda_from_high, 1),
            "soxl_price": soxl_price,
        },
        "soxl": soxl_advice,
        "buy_targets": {
            "best": f"NVIDIA ${nvda_high_52w * 0.6:.0f}以下（高値比-40%）",
            "good": f"NVIDIA ${nvda_high_52w * 0.7:.0f}以下（高値比-30%）",
            "consider": f"NVIDIA ${nvda_high_52w * 0.8:.0f}以下（高値比-20%）",
            "current": f"NVIDIA ${nvda_price}（高値比{nvda_from_high:.0f}%）",
        },
    }


def evaluate_broad_market(
    crash_score: float, sp500_price: float, sp500_high: float,
    fear_greed: float, vix: float
) -> dict:
    """
    広域市場（S&P500 / オルカン）の投入判定

    NISA成長枠240万を4回に分けて投入する戦略
    """
    if sp500_price is None or crash_score is None:
        return _unknown("広域市場", "データ取得失敗")

    sp500_from_high = ((sp500_price - sp500_high) / sp500_high) * 100 if sp500_high else 0

    # 段階判定
    if crash_score <= 20 and sp500_from_high <= -15:
        signal = "STRONG_BUY"
        action = "NISA残り全額投入。S&P500 + オルカンに分散"
        urgency = "high"
        tranche = "4回目（残り全額）"
        reason = f"Crash Score {crash_score} + S&P500 高値比{sp500_from_high:.0f}%。底打ち接近"
    elif crash_score <= 30 and sp500_from_high <= -10:
        signal = "BUY"
        action = "NISA 2〜3回目投入（各60万）。eMAXIS Slim S&P500"
        urgency = "high"
        tranche = "2〜3回目"
        reason = f"恐怖ゾーン入り。S&P500が高値から{sp500_from_high:.0f}%下落"
    elif sp500_from_high <= -10:
        signal = "BUY"
        action = "NISA 1回目投入（60万）。eMAXIS Slim S&P500"
        urgency = "medium"
        tranche = "1回目"
        reason = f"S&P500が高値比-10%を割った。最初の投入タイミング"
    elif crash_score <= 40:
        signal = "CONSIDER"
        action = "投入準備。S&P500がもう少し下がれば1回目投入"
        urgency = "low"
        tranche = "準備中"
        reason = f"センチメントは恐怖だがS&P500の下落幅はまだ浅い（{sp500_from_high:.0f}%）"
    else:
        signal = "WAIT"
        action = "NISA投入は待機。暴落を待つ"
        urgency = "none"
        tranche = "待機"
        reason = f"Crash Score {crash_score}。まだ恐怖ゾーンではない"

    # 6月末ルール
    deadline_note = None
    now = datetime.now()
    if now.month >= 6 and signal in ("WAIT", "WATCH"):
        deadline_note = "6月末までに暴落なし → 機会損失回避のため全額投入を検討"

    return {
        "sector": "広域市場（S&P500/オルカン）",
        "signal": signal,
        "action": action,
        "urgency": urgency,
        "reason": reason,
        "tranche": tranche,
        "deadline_note": deadline_note,
        "data": {
            "crash_score": crash_score,
            "sp500_price": sp500_price,
            "sp500_high": sp500_high,
            "sp500_from_high_pct": round(sp500_from_high, 1),
            "fear_greed": fear_greed,
            "vix": vix,
        },
        "buy_targets": {
            "tranche1": f"S&P500 {sp500_high * 0.90:.0f}以下（高値比-10%）",
            "tranche2": f"S&P500 {sp500_high * 0.85:.0f}以下（高値比-15%）",
            "tranche3": "関税再発動後の二番底 or 底打ちシグナル3/7以上",
            "tranche4": "VIX 40超→低下 + Fear&Greed 10→上昇",
            "current": f"S&P500 {sp500_price}（高値比{sp500_from_high:.0f}%）",
        },
    }


def evaluate_forex(usdjpy: float) -> dict:
    """為替リスク評価"""
    if usdjpy is None:
        return _unknown("為替", "USD/JPYデータ取得失敗")

    if usdjpy >= 160:
        risk = "HIGH"
        note = "日銀介入警戒ライン。円高急反転リスクあり"
        opportunity = "介入で円高 → 米国株の円建て価格が下がる → 買い場"
    elif usdjpy >= 155:
        risk = "MEDIUM"
        note = "円安圏。ここからさらに円安の余地は限定的"
        opportunity = "分割投入で為替リスクを時間分散"
    elif usdjpy >= 145:
        risk = "LOW"
        note = "適度な円安水準"
        opportunity = "米国株投資に良い環境"
    else:
        risk = "FAVORABLE"
        note = "円高水準。米国株の円建て価格が割安"
        opportunity = "ドル建て資産を買うチャンス"

    return {
        "sector": "為替",
        "usdjpy": usdjpy,
        "risk_level": risk,
        "note": note,
        "opportunity": opportunity,
    }


# ============================================================
# 統合アドバイス生成
# ============================================================

def generate_advice(
    crash_score: float,
    indicators: dict,
    watchlist: dict,
    geopolitical: dict,
    bottom_signals: dict = None,
) -> dict:
    """
    全データを統合して投資アドバイスを生成

    Returns:
        {
            "headline": "今のアクション（最も優先度の高い1文）",
            "sectors": { energy: {...}, semiconductor: {...}, broad_market: {...} },
            "forex": {...},
            "summary": "全体サマリー",
            "updated_at": "...",
        }
    """
    # WTI取得
    wti = geopolitical.get("wti", {}).get("value")

    # XLE取得
    xle_data = watchlist.get("XLE", {})
    xle_price = xle_data.get("price")
    xle_high = xle_data.get("high_52w")

    # NVIDIA取得
    nvda_data = watchlist.get("NVDA", {})
    nvda_price = nvda_data.get("price")
    nvda_high = nvda_data.get("high_52w")

    # SOXL取得
    soxl_data = watchlist.get("SOXL", {})
    soxl_price = soxl_data.get("price")

    # S&P500取得（MA deviationのprice/maから推定、またはRSIのtickerから）
    sp500_price = None
    sp500_high = None
    ma_data = indicators.get("ma_deviation", {})
    if ma_data.get("price"):
        sp500_price = ma_data["price"]
        # 52週高値はwatchlistにないので、MA + 乖離率から推定
        # 正確にはSPY 1年データが必要だが、ここでは概算
    # watchlistにSPYを追加するのが理想だが、既存データで対応
    # 仮に7002（2026/1/28の高値）をハードコード → 将来的にAPI化
    sp500_high = 7002  # TODO: yfinanceから動的取得に変更

    # Fear & Greed / VIX
    fear_greed = indicators.get("fear_greed", {}).get("value")
    vix = indicators.get("vix", {}).get("value")

    # USD/JPY
    usdjpy = geopolitical.get("usdjpy", {}).get("value")

    # セクター別評価
    energy = evaluate_energy(wti, xle_price, xle_high)
    semi = evaluate_semiconductor(nvda_price, nvda_high, soxl_price, crash_score)
    broad = evaluate_broad_market(crash_score, sp500_price, sp500_high, fear_greed, vix)
    forex = evaluate_forex(usdjpy)

    # 最も緊急度の高いアクションをヘッドラインに
    all_sectors = [energy, semi, broad]
    urgency_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    all_sectors.sort(key=lambda s: urgency_order.get(s.get("urgency", "none"), 3))

    top = all_sectors[0]
    if top["urgency"] == "high":
        headline = f"【今すぐ検討】{top['action']}"
    elif top["urgency"] == "medium":
        headline = f"【検討推奨】{top['action']}"
    elif top["urgency"] == "low":
        headline = f"【準備開始】{top['action']}"
    else:
        headline = "【待機】全セクター条件未達。次のシグナルを待つ"

    # 全体サマリー
    active_signals = [s for s in all_sectors if s["signal"] in ("BUY", "STRONG_BUY")]
    if active_signals:
        summary = f"{len(active_signals)}セクターで買いシグナル発動中"
    elif any(s["signal"] == "CONSIDER" for s in all_sectors):
        summary = "一部セクターで買い検討圏。条件が整えば投入"
    else:
        summary = "全セクター待機中。暴落を待つ戦略を継続"

    # 底打ちシグナルとの連動
    bottom_note = None
    if bottom_signals:
        met = bottom_signals.get("met_count", 0)
        total = bottom_signals.get("total_conditions", 7)
        if met >= 5:
            bottom_note = f"底打ちシグナル {met}/{total} 成立。残り全額投入を強く推奨"
        elif met >= 3:
            bottom_note = f"底打ちシグナル {met}/{total} 成立。買い場が近い"
        elif bottom_signals.get("selling_climax"):
            bottom_note = "セリングクライマックス検出。歴史的買い場の可能性"

    return {
        "headline": headline,
        "summary": summary,
        "bottom_note": bottom_note,
        "sectors": {
            "energy": energy,
            "semiconductor": semi,
            "broad_market": broad,
        },
        "forex": forex,
        "strategy_params": STRATEGY,
        "updated_at": datetime.now().isoformat(),
    }


def _unknown(sector: str, error: str) -> dict:
    return {
        "sector": sector,
        "signal": "UNKNOWN",
        "action": f"判定不能: {error}",
        "urgency": "none",
        "reason": error,
        "data": {},
    }
