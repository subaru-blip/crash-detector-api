"""
Crash Detector - Score Engine
8つの指標を統合してCrash Score（0〜100）を算出する
0 = 極度の恐怖（買い検討）、100 = 極度の強欲（売り検討）
"""


def score_vix(value: float) -> float:
    """VIX → スコア変換"""
    if value is None:
        return 50
    if value >= 50:
        return 5
    if value >= 40:
        return 15
    if value >= 30:
        return 30
    if value >= 20:
        return 50
    return 70


def score_fear_greed(value: float) -> float:
    """CNN Fear & Greed → スコア変換（そのまま使える）"""
    if value is None:
        return 50
    return value


def score_rsi(value: float) -> float:
    """RSI → スコア変換"""
    if value is None:
        return 50
    if value < 20:
        return 5
    if value < 30:
        return 20
    if value < 50:
        return 40
    if value < 70:
        return 60
    return 85


def score_credit_spread(value_bps: float) -> float:
    """クレジットスプレッド(bps) → スコア変換"""
    if value_bps is None:
        return 50
    if value_bps >= 1000:
        return 10
    if value_bps >= 500:
        return 30
    if value_bps >= 300:
        return 50
    return 75


def score_pcr(value: float) -> float:
    """プットコールレシオ → スコア変換"""
    if value is None:
        return 50
    if value >= 1.5:
        return 10
    if value >= 1.2:
        return 25
    if value >= 0.8:
        return 50
    return 85


def score_aaii_bear(value: float) -> float:
    """AAII弱気比率(%) → スコア変換"""
    if value is None:
        return 50
    if value >= 60:
        return 10
    if value >= 50:
        return 25
    if value >= 30:
        return 50
    return 75


def score_ma_deviation(value: float) -> float:
    """200日線乖離率(%) → スコア変換"""
    if value is None:
        return 50
    if value <= -20:
        return 5
    if value <= -10:
        return 20
    if value <= -5:
        return 40
    if value <= 5:
        return 55
    return 80


def score_yield_curve(value: float) -> float:
    """イールドカーブ（10Y-2Y） → スコア変換"""
    if value is None:
        return 50
    if value < -0.5:
        return 25
    if value < 0:
        return 35
    if value < 0.5:
        return 50
    return 60


# 重み付け
WEIGHTS = {
    "vix": 0.20,
    "fear_greed": 0.15,
    "rsi": 0.15,
    "credit_spread": 0.15,
    "pcr": 0.10,
    "aaii_bear": 0.10,
    "ma_deviation": 0.10,
    "yield_curve": 0.05,
}


def calculate_crash_score(indicators: dict) -> dict:
    """
    全指標を統合してCrash Scoreを算出

    Args:
        indicators: {
            "vix": {"value": 35.2},
            "fear_greed": {"value": 22},
            "rsi": {"value": 28.5},
            "credit_spread": {"value": 520},
            "pcr": {"value": 1.35},
            "aaii_bear": {"value": 52},
            "ma_deviation": {"value": -8.2},
            "yield_curve": {"value": -0.15},
        }

    Returns:
        {
            "score": 32,
            "label": "恐怖",
            "color": "orange",
            "action": "注視",
            "components": {...},
            "bottom_signals": {...},
        }
    """
    scorers = {
        "vix": score_vix,
        "fear_greed": score_fear_greed,
        "rsi": score_rsi,
        "credit_spread": score_credit_spread,
        "pcr": score_pcr,
        "aaii_bear": score_aaii_bear,
        "ma_deviation": score_ma_deviation,
        "yield_curve": score_yield_curve,
    }

    components = {}
    weighted_sum = 0

    for key, scorer in scorers.items():
        raw = indicators.get(key, {})
        value = raw.get("value")
        sub_score = scorer(value)
        weight = WEIGHTS[key]
        weighted_sum += sub_score * weight
        components[key] = {
            "raw": value,
            "score": round(sub_score, 1),
            "weight": weight,
            "weighted": round(sub_score * weight, 1),
        }

    total = round(weighted_sum, 1)

    # ラベル・色・アクション
    if total <= 20:
        label, color, action = "極度の恐怖", "red", "買い検討ゾーン"
    elif total <= 40:
        label, color, action = "恐怖", "orange", "注視"
    elif total <= 60:
        label, color, action = "中立", "yellow", "通常運用"
    elif total <= 80:
        label, color, action = "強欲", "green", "利確検討"
    else:
        label, color, action = "極度の強欲", "purple", "売り検討ゾーン"

    # 底打ちシグナル判定
    bottom_signals = check_bottom_signals(indicators)

    return {
        "score": total,
        "label": label,
        "color": color,
        "action": action,
        "components": components,
        "bottom_signals": bottom_signals,
    }


def check_bottom_signals(indicators: dict) -> dict:
    """底打ちシグナルの条件チェック（7条件中3つ以上でアラート）"""
    conditions = {}

    # 1. VIX > 40
    vix = indicators.get("vix", {}).get("value")
    conditions["vix_gt_40"] = {
        "label": "VIX > 40",
        "met": vix is not None and vix > 40,
        "value": vix,
    }

    # 2. Fear & Greed < 25
    fg = indicators.get("fear_greed", {}).get("value")
    conditions["fg_lt_25"] = {
        "label": "Fear&Greed < 25",
        "met": fg is not None and fg < 25,
        "value": fg,
    }

    # 3. RSI < 30
    rsi = indicators.get("rsi", {}).get("value")
    conditions["rsi_lt_30"] = {
        "label": "RSI < 30",
        "met": rsi is not None and rsi < 30,
        "value": rsi,
    }

    # 4. AAII弱気 > 50%
    aaii = indicators.get("aaii_bear", {}).get("value")
    conditions["aaii_gt_50"] = {
        "label": "AAII弱気 > 50%",
        "met": aaii is not None and aaii > 50,
        "value": aaii,
    }

    # 5. PCR > 1.2
    pcr = indicators.get("pcr", {}).get("value")
    conditions["pcr_gt_1_2"] = {
        "label": "PCR > 1.2",
        "met": pcr is not None and pcr > 1.2,
        "value": pcr,
    }

    # 6. 200日線乖離率 < -10%
    ma = indicators.get("ma_deviation", {}).get("value")
    conditions["ma_lt_neg10"] = {
        "label": "MA乖離 < -10%",
        "met": ma is not None and ma < -10,
        "value": ma,
    }

    # 7. クレジットスプレッド > 500bps
    cs = indicators.get("credit_spread", {}).get("value")
    conditions["cs_gt_500"] = {
        "label": "HYスプレッド > 500bps",
        "met": cs is not None and cs > 500,
        "value": cs,
    }

    met_count = sum(1 for c in conditions.values() if c["met"])

    # セリングクライマックス判定
    selling_climax = (
        rsi is not None and rsi < 20
        and vix is not None and vix > 50
    )

    return {
        "conditions": conditions,
        "met_count": met_count,
        "total_conditions": 7,
        "alert": met_count >= 3,
        "alert_level": (
            "セリングクライマックス" if selling_climax
            else "底打ちシグナル" if met_count >= 3
            else "条件未達"
        ),
        "selling_climax": selling_climax,
    }
