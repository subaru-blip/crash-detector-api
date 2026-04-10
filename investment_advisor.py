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
    "total_budget": 2970000,  # 297万（成長投資枠 + 特定口座）
    "nisa_growth_budget": 2400000,   # 成長投資枠 240万（SBI証券・新NISA）
    "nisa_tsumitate_budget": 1200000,  # つみたて投資枠 120万（SBI証券・毎月10万で自動積立済み）
    "tokutei_budget": 570000, # 特定口座 57万（楽天証券）
    "brokers": {
        "nisa": "SBI証券（新NISA）",
        "tokutei": "楽天証券（特定口座）",
    },
    "notes": "つみたて投資枠120万は毎月10万の自動積立で使用済み。ツールで管理するのは成長投資枠+特定口座の297万",
    "tranches": [
        {"label": "1回目", "amount": 600000, "account": "nisa", "status": "done", "date": "2026-04-07", "ticker": "eMAXIS Slim S&P500"},
        {"label": "2回目", "amount": 600000, "account": "nisa", "status": "pending"},
        {"label": "3回目", "amount": 600000, "account": "nisa", "status": "pending"},
        {"label": "4回目", "amount": 600000, "account": "nisa", "status": "pending"},
    ],
}

# 約定ラグ情報（注文してから実際に買えるまでの日数）
SETTLEMENT_LAG = {
    "emaxis_sp500": {"name": "eMAXIS Slim S&P500", "days": 2, "note": "注文翌営業日の基準価額で約定、受渡は約定+2営業日"},
    "emaxis_allcountry": {"name": "eMAXIS Slim 全世界株式", "days": 2, "note": "注文翌営業日の基準価額で約定"},
    "xle": {"name": "XLE（エネルギーETF）", "days": 1, "note": "海外ETF。注文当日〜翌営業日に約定"},
    "nvda": {"name": "NVIDIA", "days": 1, "note": "米国個別株。注文当日〜翌営業日に約定"},
    "soxl": {"name": "SOXL", "days": 1, "note": "米国ETF。注文当日〜翌営業日に約定"},
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
        signal = "STRONG_BUY"
        action = f"SBI証券でXLE（エネルギーETF）を60万円分、今すぐ注文してください"
        urgency = "high"
        reason = f"原油が${wti_price}まで下がりました。停戦後のバーゲン価格です。注文から翌営業日に買えます"
    elif wti_price <= 90:
        signal = "BUY"
        action = f"SBI証券でXLE（エネルギーETF）を60万円分、今週中に注文してください"
        urgency = "medium"
        reason = f"原油が${wti_price}に調整中。この水準なら買っても大丈夫です"
    elif xle_from_high <= -20:
        signal = "BUY"
        action = f"XLEが高値から{xle_from_high:.0f}%下落。60万円分を今週中に注文してください"
        urgency = "medium"
        reason = "エネルギーETFが大幅下落中。反発すれば利益が出ます"
    elif wti_price >= 120:
        signal = "WAIT"
        action = "エネルギーはまだ買わないでください"
        urgency = "none"
        reason = f"原油${wti_price}は高すぎます。今買うと高値掴みになるリスクがあります"
    elif wti_price >= 100 and xle_from_high >= -10:
        signal = "WAIT"
        action = "エネルギーはまだ買わないでください"
        urgency = "none"
        reason = f"XLEが高値圏です。停戦が進めば急落するリスクがあります。原油${90}以下まで待ちましょう"
    else:
        signal = "WAIT"
        action = "エネルギーはまだ買わないでください"
        urgency = "none"
        reason = f"原油${wti_price}は中途半端な価格帯です。${90}以下に下がったら買い時です"

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
        action = f"楽天証券（特定口座）でNVIDIA株を25万円分、今すぐ注文してください"
        urgency = "high"
        reason = f"NVIDIAが${nvda_price}（高値から{nvda_from_high:.0f}%下落）。AIの需要は変わっていないのに異常な安さです。翌営業日に買えます"
    elif nvda_from_high <= -30:
        signal = "BUY"
        action = f"楽天証券（特定口座）でNVIDIA株を25万円分、今週中に注文してください"
        urgency = "medium"
        reason = f"NVIDIAが${nvda_price}（高値から{nvda_from_high:.0f}%下落）。決算は過去最高なのに安くなっています"
    elif nvda_from_high <= -20:
        signal = "WAIT"
        action = "NVIDIAはまだ買わないでください"
        urgency = "none"
        reason = f"${nvda_price}（高値から{nvda_from_high:.0f}%下落）。あと10%下がれば買い時です。${nvda_high_52w * 0.7:.0f}以下まで待ちましょう"
    elif nvda_from_high <= -10:
        signal = "WAIT"
        action = "NVIDIAはまだ買わないでください"
        urgency = "none"
        reason = f"${nvda_price}はまだ高いです。${nvda_high_52w * 0.7:.0f}以下まで待ちましょう"
    else:
        signal = "WAIT"
        action = "NVIDIAはまだ買わないでください"
        urgency = "none"
        reason = f"${nvda_price}は高値圏です。今買うと損する可能性が高いです"

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


def _get_next_pending_tranche() -> dict | None:
    """未消化（pending）の次のトランシェを返す。全部doneならNone"""
    for t in STRATEGY["tranches"]:
        if t["status"] == "pending":
            return t
    return None


def _count_done_tranches() -> int:
    """消化済みトランシェ数"""
    return sum(1 for t in STRATEGY["tranches"] if t["status"] == "done")


def evaluate_broad_market(
    crash_score: float, sp500_price: float, sp500_high: float,
    fear_greed: float, vix: float
) -> dict:
    """
    広域市場（S&P500 / オルカン）の投入判定

    NISA成長枠240万を4回に分けて投入する戦略
    tranchesの消化状況を見て、全て投入済みなら買いアクションを出さない
    """
    if sp500_price is None or crash_score is None:
        return _unknown("広域市場", "データ取得失敗")

    sp500_from_high = ((sp500_price - sp500_high) / sp500_high) * 100 if sp500_high else 0

    # トランシェ消化状況を確認
    next_tranche = _get_next_pending_tranche()
    done_count = _count_done_tranches()
    total_tranches = len(STRATEGY["tranches"])

    # 全トランシェ投入済み → 買いアクションを出さない
    if next_tranche is None:
        signal = "COMPLETE"
        action = f"NISA成長枠は全{total_tranches}回分を投入済みです。追加投入の枠はありません"
        urgency = "none"
        tranche = f"全{total_tranches}回投入完了"
        reason = "計画通りの投入が完了しています。売りタイミングの判定に注目してください"
    # 段階判定（未消化トランシェがある場合のみ）
    elif crash_score <= 20 and sp500_from_high <= -15:
        signal = "STRONG_BUY"
        action = "SBI証券（NISA）でeMAXIS Slim S&P500を残り全額分、今すぐ注文してください"
        urgency = "high"
        tranche = f"{next_tranche['label']}（残り{total_tranches - done_count}回分）"
        reason = f"市場の恐怖度が極限（スコア{crash_score}）で、S&P500も{sp500_from_high:.0f}%下落。歴史的な買い場です。注文から2営業日で購入完了します"
    elif crash_score <= 30 and sp500_from_high <= -10:
        signal = "BUY"
        action = f"SBI証券（NISA）でeMAXIS Slim S&P500を60万円分、今週中に注文してください（NISA {next_tranche['label']}）"
        urgency = "medium"
        tranche = next_tranche["label"]
        reason = f"市場が怖がっている（スコア{crash_score}）＋株価も{sp500_from_high:.0f}%下落。この組み合わせは買い時です"
    elif sp500_from_high <= -10:
        signal = "BUY"
        action = f"SBI証券（NISA）でeMAXIS Slim S&P500を60万円分、今週中に注文してください（NISA {next_tranche['label']}）"
        urgency = "medium"
        tranche = next_tranche["label"]
        reason = f"S&P500が高値から{sp500_from_high:.0f}%下落。4回に分けて買う{next_tranche['label']}です。注文から2営業日で購入完了します"
    elif crash_score <= 40:
        signal = "WAIT"
        action = "S&P500はまだ買わないでください"
        urgency = "none"
        tranche = f"次は{next_tranche['label']}（待機中）"
        reason = f"みんな怖がっていますが、株価の下落はまだ{sp500_from_high:.0f}%で浅いです。-10%（{sp500_high * 0.9:.0f}）以下まで待ちましょう"
    else:
        signal = "WAIT"
        action = "S&P500はまだ買わないでください"
        urgency = "none"
        tranche = f"次は{next_tranche['label']}（待機中）"
        reason = f"まだ通常の状態です。暴落が来たら教えます。{sp500_high * 0.9:.0f}以下になったら{next_tranche['label']}を買います"

    # 6月末ルール
    deadline_note = None
    now = datetime.now()
    if now.month >= 6 and signal in ("WAIT", "WATCH") and next_tranche is not None:
        deadline_note = "6月末までに暴落なし → 機会損失回避のため全額投入を検討"

    return {
        "sector": "広域市場（S&P500/オルカン）",
        "signal": signal,
        "action": action,
        "urgency": urgency,
        "reason": reason,
        "tranche": tranche,
        "done_count": done_count,
        "total_tranches": total_tranches,
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

    # 最も緊急度の高いアクションをヘッドラインに（COMPLETE除外）
    all_sectors = [energy, semi, broad]
    active_sectors = [s for s in all_sectors if s.get("signal") != "COMPLETE"]
    urgency_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    active_sectors.sort(key=lambda s: urgency_order.get(s.get("urgency", "none"), 3))

    if active_sectors:
        top = active_sectors[0]
        if top["urgency"] == "high":
            headline = f"今すぐ注文してください → {top['action']}"
        elif top["urgency"] == "medium":
            headline = f"今週中に注文を検討 → {top['action']}"
        elif top["urgency"] == "low":
            headline = f"まだ買わないでください。もう少しで条件達成です"
        else:
            headline = "まだ買わないでください。条件が揃うまで待ちましょう"
    else:
        headline = "全セクター投入完了。売りタイミングの判定に注目してください"

    # 全体サマリー
    active_signals = [s for s in all_sectors if s["signal"] in ("BUY", "STRONG_BUY")]
    complete_signals = [s for s in all_sectors if s["signal"] == "COMPLETE"]
    if active_signals:
        summary = f"{len(active_signals)}セクターで買いシグナル発動中"
    elif any(s["signal"] == "CONSIDER" for s in all_sectors):
        summary = "一部セクターで買い検討圏。条件が整えば投入"
    elif complete_signals:
        done = _count_done_tranches()
        total = len(STRATEGY["tranches"])
        summary = f"NISA {done}/{total}回投入済み。残りセクターは待機中"
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
        "settlement_lag": SETTLEMENT_LAG,
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
