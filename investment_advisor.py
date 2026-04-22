"""
Investment Advisor Engine v2（2026-04-22 刷新）
清水さん個人の投資判断ツール。銘柄マスタ/計画/保有/売り判定3ルールを統合。

設計思想:
- SYMBOLS: 銘柄の日本語名・証券会社・注文方法のマスタ（表示はここから生成）
- PLAN: 未投入のトランシェ計画。口座枠ごとに発動条件を明示
- PORTFOLIO: 保有実績。売り判定はこれを対象にする
- MACRO_SIGNALS: 5条件（Crash Score/Fear&Greed/VIX/RSI/S&P500高値圏）
- 売り判定3ルール:
    ルール1: マクロ過熱×含み益（NISA/特定口座で閾値差）
    ルール2: 含み益+100%到達で機械的に半分利確
    ルール3: レバETF特別（+50%半分、+100%全部、30日横ばい全部）

戦略書: docs/investment-strategy-2026Q2.md と同期すること
"""

from datetime import datetime


# ============================================================
# 銘柄マスタ
# ============================================================
SYMBOLS = {
    "emaxis_sp500": {
        "name": "eMAXIS Slim 米国株式（S&P500）",
        "short_name": "eMAXIS S&P500",
        "ticker_display": "eMAXIS Slim S&P500",
        "proxy_ticker": "SPY",
        "type": "investment_trust",
        "broker": "SBI証券",
        "broker_section": "投資信託",
        "search_keyword": "eMAXIS Slim 米国株式",
        "order_method": "金額指定（円建て）",
        "settlement_days": 2,
        "category": "米国株式インデックス",
        "is_leveraged": False,
        "note": "S&P500連動の投資信託。低コスト（信託報酬0.09%）",
    },
    "emaxis_allcountry": {
        "name": "eMAXIS Slim 全世界株式（オール・カントリー）",
        "short_name": "オルカン",
        "ticker_display": "eMAXIS Slim オルカン",
        "proxy_ticker": "VT",
        "type": "investment_trust",
        "broker": "SBI証券",
        "broker_section": "投資信託",
        "search_keyword": "eMAXIS Slim 全世界",
        "order_method": "金額指定（円建て）",
        "settlement_days": 2,
        "category": "全世界株式",
        "is_leveraged": False,
        "note": "世界中の株式に分散。米国比率は約6割",
    },
    "xle": {
        "name": "XLE（米国エネルギーセクターETF）",
        "short_name": "XLE エネルギー",
        "ticker_display": "XLE",
        "proxy_ticker": "XLE",
        "type": "us_etf",
        "broker": "SBI証券",
        "broker_section": "外国株式 > 米国株式 > ETF検索",
        "search_keyword": "XLE",
        "order_method": "株数指定（ドル建て）",
        "settlement_days": 3,
        "category": "エネルギーセクター",
        "is_leveraged": False,
        "note": "ExxonMobil・Chevron等を含む米国エネルギー大手ETF",
    },
    "nvda": {
        "name": "NVIDIA（エヌビディア）",
        "short_name": "NVIDIA",
        "ticker_display": "NVDA",
        "proxy_ticker": "NVDA",
        "type": "us_stock",
        "broker": "楽天証券",
        "broker_section": "外国株式 > 米国株式",
        "search_keyword": "NVDA",
        "order_method": "株数指定（ドル建て）",
        "settlement_days": 3,
        "category": "AI半導体",
        "is_leveraged": False,
        "note": "AI半導体の王者。成長性は高いが単価も高い",
    },
    "soxl": {
        "name": "SOXL（半導体ブル3倍ETF）",
        "short_name": "SOXL 半導体3倍",
        "ticker_display": "SOXL",
        "proxy_ticker": "SOXL",
        "type": "us_etf_leveraged",
        "broker": "楽天証券",
        "broker_section": "外国株式 > 米国株式 > ETF検索",
        "search_keyword": "SOXL",
        "order_method": "株数指定（ドル建て）",
        "settlement_days": 3,
        "category": "半導体レバレッジ",
        "is_leveraged": True,
        "note": "半導体指数の3倍連動。長期保有は減衰注意。底値での一発狙い",
    },
    "gld_nisa": {
        "name": "グローバルX ゴールド・トラスト（425A）",
        "short_name": "ゴールドETF(425A)",
        "ticker_display": "425A",
        "proxy_ticker": "GLD",
        "type": "jp_etf",
        "broker": "SBI証券",
        "broker_section": "国内株式 > ETF > 銘柄コード",
        "search_keyword": "425A",
        "order_method": "株数指定（円建て）",
        "settlement_days": 3,
        "category": "ゴールド",
        "is_leveraged": False,
        "note": "東証上場のゴールドETF。NISA成長枠で買える",
    },
    "gdx": {
        "name": "GDX（NYSE金鉱株ETF）",
        "short_name": "GDX 金鉱株",
        "ticker_display": "GDX",
        "proxy_ticker": "GDX",
        "type": "us_etf",
        "broker": "楽天証券",
        "broker_section": "外国株式 > 米国株式 > ETF検索",
        "search_keyword": "GDX",
        "order_method": "株数指定（ドル建て）",
        "settlement_days": 3,
        "category": "金鉱株",
        "is_leveraged": False,
        "note": "金鉱会社ETF。金価格上昇時にゴールド本体より大きく動く",
    },
    "xom": {
        "name": "エクソンモービル",
        "short_name": "XOM",
        "ticker_display": "XOM",
        "proxy_ticker": "XOM",
        "type": "us_stock",
        "broker": "楽天証券",
        "broker_section": "外国株式 > 米国株式",
        "search_keyword": "XOM",
        "order_method": "株数指定（ドル建て）",
        "settlement_days": 3,
        "category": "エネルギー個別",
        "is_leveraged": False,
        "note": "世界最大級の石油メジャー。高配当",
    },
}

# 口座マスタ
ACCOUNTS = {
    "nisa_growth": {
        "label": "NISA成長投資枠",
        "broker": "SBI証券",
        "annual_limit": 2400000,  # 240万/年
        "tax_free": True,
        "note": "非課税。売却しても当年枠は戻らない（翌年復活）",
    },
    "tokutei": {
        "label": "特定口座",
        "broker": "楽天証券",
        "annual_limit": 570000,  # 57万（清水さんの自己設定）
        "tax_free": False,
        "tax_rate": 0.20315,  # 譲渡益税
        "note": "売却益に20.315%課税。いつでも買い戻し可能",
    },
    "nisa_tsumitate": {
        "label": "NISAつみたて投資枠",
        "broker": "SBI証券",
        "annual_limit": 1200000,
        "tax_free": True,
        "managed_by_tool": False,  # ツール対象外
        "note": "個人で毎月10万自動積立中。ツールでは管理しない（長期保有固定）",
    },
}


# ============================================================
# 投入計画（未投入トランシェ）
# ============================================================
PLAN = [
    # --- NISA成長枠（残180万）---
    {
        "slot": "nisa_tranche2",
        "account": "nisa_growth",
        "symbol": "emaxis_sp500",
        "amount": 600000,
        "label": "2回目投入",
        "priority": 1,
        "condition": {"type": "sp500_from_high", "value": -10},
        "condition_text": "S&P500（SPY）が高値から-10%以下まで下落",
    },
    {
        "slot": "nisa_tranche3",
        "account": "nisa_growth",
        "symbol": "emaxis_sp500",
        "amount": 600000,
        "label": "3回目投入",
        "priority": 2,
        "condition": {"type": "sp500_from_high", "value": -15},
        "condition_text": "S&P500（SPY）が高値から-15%以下 or 関税再発動後の二番底",
    },
    {
        "slot": "nisa_gold",
        "account": "nisa_growth",
        "symbol": "gld_nisa",
        "amount": 300000,
        "label": "ゴールド枠",
        "priority": 3,
        "condition": {"type": "gold_from_high", "value": -5},
        "condition_text": "金が高値から-5%調整 or Crash Score 30以下",
    },
    {
        "slot": "nisa_reserve",
        "account": "nisa_growth",
        "symbol": "emaxis_sp500",
        "amount": 300000,
        "label": "予備枠（S&P500 or XLE）",
        "priority": 4,
        "condition": {"type": "bottom_signals", "value": 3},
        "condition_text": "底打ちシグナル3/7以上 or エネルギー急落（WTI $90以下）",
    },
    # --- 特定口座（残57万）---
    {
        "slot": "tokutei_nvda",
        "account": "tokutei",
        "symbol": "nvda",
        "amount": 200000,
        "label": "AI半導体メイン",
        "priority": 1,
        "condition": {"type": "nvda_from_high", "value": -30},
        "condition_text": "NVIDIAが高値から-30%以下",
    },
    {
        "slot": "tokutei_soxl",
        "account": "tokutei",
        "symbol": "soxl",
        "amount": 150000,
        "label": "半導体3倍レバ（一発狙い）",
        "priority": 2,
        "condition": {"type": "soxl_and_crash", "value": {"soxl_max": 30, "crash_max": 20}},
        "condition_text": "SOXL $30以下 かつ Crash Score 20以下",
    },
    {
        "slot": "tokutei_gold",
        "account": "tokutei",
        "symbol": "gdx",
        "amount": 120000,
        "label": "金鉱株",
        "priority": 3,
        "condition": {"type": "gold_from_high", "value": -10},
        "condition_text": "金が高値から-10%調整",
    },
    {
        "slot": "tokutei_energy",
        "account": "tokutei",
        "symbol": "xom",
        "amount": 100000,
        "label": "エネルギー個別",
        "priority": 4,
        "condition": {"type": "wti_price_above", "value": 120},
        "condition_text": "WTI原油 $120超で封鎖長期化確認時",
    },
]


# ============================================================
# 保有実績（手動管理。購入報告があれば追記する）
# ============================================================
PORTFOLIO = [
    {
        "slot": "nisa_tranche1",
        "symbol": "emaxis_sp500",
        "account": "nisa_growth",
        "invested_amount": 600000,
        "invested_date": "2026-04-07",
        "proxy_price_at_buy": 679.91,  # 購入日のSPY価格（概算評価用）
        "note": "1回目投入",
    },
]


# ============================================================
# 買い戻しキュー（利確した資金の再投入予約）
# ============================================================
# 利確実行時に自動追加される。3段階ラダーで Crash Score に応じて買い戻す。
# NISA枠は売却しても当年枠が戻らないため、買い戻し先は特定口座（楽天証券）。
#
# データ例（利確を実行すると以下のような構造が追加される）:
# {
#     "id": "buyback_20260815_01",
#     "sold_date": "2026-08-15",
#     "sold_amount": 200000,
#     "sold_from_account": "nisa_growth",
#     "sold_symbol": "emaxis_sp500",
#     "reason": "マクロ3/5成立+含み益+30% → 30%利確",
#     "stages": [
#         {"label": "1段目", "amount": 66000, "target_symbol": "emaxis_sp500",
#          "target_account": "tokutei", "trigger": {"type": "crash_below", "value": 50},
#          "condition_text": "Crash Score 50以下で発動", "status": "pending"},
#         {"label": "2段目", "amount": 66000, "target_symbol": "emaxis_sp500",
#          "target_account": "tokutei", "trigger": {"type": "crash_below", "value": 30},
#          "condition_text": "Crash Score 30以下で発動", "status": "pending"},
#         {"label": "3段目", "amount": 68000, "target_symbol": "emaxis_sp500",
#          "target_account": "tokutei", "trigger": {"type": "bottom_or_crash", "value": 20},
#          "condition_text": "Crash 20以下 or 底打ちシグナル3/7以上", "status": "pending"},
#     ],
# }
BUYBACK_QUEUE = []


def make_buyback_entry(sold_date, sold_amount, sold_from_account, sold_symbol, reason,
                        target_symbol=None, target_account="tokutei"):
    """利確時に3段階ラダーの買い戻し予約を生成するヘルパー"""
    if target_symbol is None:
        target_symbol = sold_symbol
    third = sold_amount // 3
    remainder = sold_amount - third * 2  # 端数を3段目に寄せる
    entry_id = f"buyback_{sold_date.replace('-', '')}_{sold_symbol}"
    return {
        "id": entry_id,
        "sold_date": sold_date,
        "sold_amount": sold_amount,
        "sold_from_account": sold_from_account,
        "sold_symbol": sold_symbol,
        "reason": reason,
        "stages": [
            {"label": "1段目", "amount": third, "target_symbol": target_symbol,
             "target_account": target_account,
             "trigger": {"type": "crash_below", "value": 50},
             "condition_text": "Crash Score 50以下で発動", "status": "pending"},
            {"label": "2段目", "amount": third, "target_symbol": target_symbol,
             "target_account": target_account,
             "trigger": {"type": "crash_below", "value": 30},
             "condition_text": "Crash Score 30以下で発動", "status": "pending"},
            {"label": "3段目", "amount": remainder, "target_symbol": target_symbol,
             "target_account": target_account,
             "trigger": {"type": "bottom_or_crash", "value": 20},
             "condition_text": "Crash 20以下 or 底打ちシグナル3/7以上で発動",
             "status": "pending"},
        ],
    }


def _evaluate_buyback_trigger(trigger, crash_score, bottom_signals_met):
    ttype = trigger["type"]
    value = trigger["value"]
    if ttype == "crash_below":
        return crash_score is not None and crash_score <= value
    if ttype == "bottom_or_crash":
        if bottom_signals_met >= 3:
            return True
        return crash_score is not None and crash_score <= value
    return False


def build_buyback_summary(crash_score, bottom_signals_met):
    """買い戻しキューの全体状況を返す"""
    active_actions = []
    total_pending = 0
    for entry in BUYBACK_QUEUE:
        for stage in entry["stages"]:
            if stage.get("status") != "pending":
                continue
            total_pending += stage["amount"]
            fired = _evaluate_buyback_trigger(stage["trigger"], crash_score, bottom_signals_met)
            sym = SYMBOLS.get(stage["target_symbol"], {})
            acc = ACCOUNTS.get(stage["target_account"], {})
            if fired:
                active_actions.append({
                    "type": "buyback",
                    "urgency": "medium",
                    "ready": True,
                    "entry_id": entry["id"],
                    "stage_label": stage.get("label", ""),
                    "amount": stage["amount"],
                    "amount_text": f"{stage['amount']:,}円",
                    "symbol_name": sym.get("name", stage["target_symbol"]),
                    "short_name": sym.get("short_name", stage["target_symbol"]),
                    "account": acc.get("label", stage["target_account"]),
                    "broker": sym.get("broker", ""),
                    "broker_section": sym.get("broker_section", ""),
                    "search_keyword": sym.get("search_keyword", ""),
                    "order_method": sym.get("order_method", ""),
                    "condition_text": stage.get("condition_text", ""),
                    "original_reason": entry.get("reason", ""),
                    "sold_date": entry.get("sold_date"),
                })
    return {
        "entries": BUYBACK_QUEUE,
        "total_pending": total_pending,
        "active_actions": active_actions,
        "queue_count": len(BUYBACK_QUEUE),
    }


# ============================================================
# つみたて枠の大暴落警告（マクロ5/5フル成立時のみ通知）
# ============================================================
# つみたて枠（131万相当）は売り判定対象外（完全HOLD）。
# ただし、市場が極端に過熱（マクロ5/5フル成立）した時のみ、
# 「SBI画面で含み益+100%超を確認したら半分利確検討」と通知する。
TSUMITATE_HOLDINGS_NOTE = {
    "sbi_v_all_us": "SBI・V・全米株式インデックスファンド（約101万）",
    "emaxis_sp500_tsumitate": "eMAXIS Slim 米国株式(S&P500)（約10万）",
    "emaxis_allcountry_tsumitate": "eMAXIS Slim 全世界株式(オルカン)（約20万）",
}


def evaluate_tsumitate_warning(macro):
    """つみたて枠への大暴落警告（5/5フル成立時のみ）"""
    met = macro["met_count"]
    if met >= 5:
        return {
            "level": "WARNING",
            "headline": "⚠️ つみたて枠の利確検討タイミング",
            "detail": (
                "市場が歴史的な過熱水準（5/5条件成立）に達しています。"
                "SBI証券の「保有商品一覧」画面で、つみたて枠3銘柄の評価損益率を確認してください。"
                "含み益が+100%を超えていれば半分利確を、+50%以上なら30%利確を検討してください。"
            ),
            "guide": "SBI証券 → 口座管理 → 保有商品一覧 → 「評価損益率」列をチェック",
            "holdings_note": TSUMITATE_HOLDINGS_NOTE,
        }
    if met >= 4:
        return {
            "level": "CAUTION",
            "headline": "つみたて枠の含み益率を把握しておいてください",
            "detail": (
                "マクロ過熱4/5成立。5/5到達すれば、つみたて枠の部分利確検討フェーズに入ります。"
                "今のうちにSBI画面で評価損益率を確認しておくと、判断がスムーズです。"
            ),
            "guide": "SBI証券 → 口座管理 → 保有商品一覧",
            "holdings_note": TSUMITATE_HOLDINGS_NOTE,
        }
    return None


# ============================================================
# マクロシグナル判定（売り5条件）
# ============================================================
def evaluate_macro_signals(crash_score, fear_greed, vix, rsi, sp500_price, sp500_high):
    """5条件のマクロ過熱シグナルを判定"""
    signals = []

    # 条件1: Crash Score 80+
    if crash_score is not None and crash_score >= 80:
        signals.append({"key": "crash_score", "label": "市場の過熱度（Crash Score 80+）", "met": True,
                        "severity": "high", "detail": f"Crash Score {crash_score:.0f} → 極度の強欲圏"})
    elif crash_score is not None and crash_score >= 70:
        signals.append({"key": "crash_score", "label": "市場の過熱度（Crash Score 70+）", "met": True,
                        "severity": "medium", "detail": f"Crash Score {crash_score:.0f} → 強欲圏入り"})
    else:
        cs_str = f"{crash_score:.0f}" if crash_score is not None else "N/A"
        signals.append({"key": "crash_score", "label": "市場の過熱度（Crash Score 80+）", "met": False,
                        "severity": "none", "detail": f"Crash Score {cs_str} → まだ過熱していない"})

    # 条件2: Fear & Greed 80+
    if fear_greed is not None and fear_greed >= 80:
        signals.append({"key": "fear_greed", "label": "市場心理（Fear&Greed 80+）", "met": True,
                        "severity": "high", "detail": f"Fear&Greed {fear_greed:.0f} → 極度の強欲"})
    elif fear_greed is not None and fear_greed >= 70:
        signals.append({"key": "fear_greed", "label": "市場心理（Fear&Greed 70+）", "met": True,
                        "severity": "medium", "detail": f"Fear&Greed {fear_greed:.0f} → 強欲"})
    else:
        signals.append({"key": "fear_greed", "label": "市場心理（Fear&Greed 80+）", "met": False,
                        "severity": "none", "detail": f"Fear&Greed {fear_greed if fear_greed is not None else 'N/A'} → 楽観的すぎない"})

    # 条件3: VIX 12以下（油断）
    if vix is not None and vix <= 12:
        signals.append({"key": "vix", "label": "恐怖指数（VIX 12以下=油断）", "met": True,
                        "severity": "high", "detail": f"VIX {vix:.1f} → 市場が油断している"})
    elif vix is not None and vix <= 15:
        signals.append({"key": "vix", "label": "恐怖指数（VIX 15以下）", "met": True,
                        "severity": "medium", "detail": f"VIX {vix:.1f} → 警戒感低下"})
    else:
        vix_str = f"{vix:.1f}" if vix is not None else "N/A"
        signals.append({"key": "vix", "label": "恐怖指数（VIX 12以下=油断）", "met": False,
                        "severity": "none", "detail": f"VIX {vix_str} → 市場は警戒している"})

    # 条件4: RSI 75+
    if rsi is not None and rsi >= 75:
        signals.append({"key": "rsi", "label": "RSI買われすぎ（75+）", "met": True,
                        "severity": "high", "detail": f"RSI {rsi:.0f} → 買われすぎ水準"})
    elif rsi is not None and rsi >= 70:
        signals.append({"key": "rsi", "label": "RSIやや過熱（70+）", "met": True,
                        "severity": "medium", "detail": f"RSI {rsi:.0f} → やや過熱"})
    else:
        rsi_str = f"{rsi:.0f}" if rsi is not None else "N/A"
        signals.append({"key": "rsi", "label": "RSI買われすぎ（75+）", "met": False,
                        "severity": "none", "detail": f"RSI {rsi_str} → 過熱していない"})

    # 条件5: S&P500高値圏（高値比-1%以内）
    sp500_from_high = None
    if sp500_price and sp500_high:
        sp500_from_high = ((sp500_price - sp500_high) / sp500_high) * 100
        if sp500_from_high >= -1:
            signals.append({"key": "sp500_high", "label": "S&P500高値圏（高値比-1%以内）", "met": True,
                            "severity": "medium", "detail": f"S&P500 高値比 {sp500_from_high:.1f}% → 最高値付近"})
        else:
            signals.append({"key": "sp500_high", "label": "S&P500高値圏（高値比-1%以内）", "met": False,
                            "severity": "none", "detail": f"S&P500 高値比 {sp500_from_high:.1f}% → 高値圏ではない"})
    else:
        signals.append({"key": "sp500_high", "label": "S&P500高値圏（高値比-1%以内）", "met": False,
                        "severity": "none", "detail": "S&P500データなし"})

    met_count = sum(1 for s in signals if s["met"])
    high_count = sum(1 for s in signals if s["met"] and s["severity"] == "high")
    return {
        "signals": signals,
        "met_count": met_count,
        "high_count": high_count,
        "total": len(signals),
    }


# ============================================================
# ポートフォリオ評価（概算）
# ============================================================
def _current_price(symbol_key, watchlist, geopolitical, sp500_price):
    """銘柄の概算現在価格（プロキシ銘柄ベース）"""
    sym = SYMBOLS.get(symbol_key, {})
    proxy = sym.get("proxy_ticker")
    if proxy in watchlist and watchlist[proxy].get("price"):
        return watchlist[proxy]["price"]
    # プロキシが取れない場合の代替
    if symbol_key in ("emaxis_sp500",):
        return sp500_price  # SPYで代用
    if symbol_key in ("gld_nisa",):
        gld = watchlist.get("GLD", {})
        return gld.get("price")
    return None


def evaluate_holding_sell(holding, macro, watchlist, geopolitical, sp500_price, rsi):
    """
    保有銘柄1つの売り判定（3ルール）
    - ルール1: マクロ過熱×含み益
    - ルール2: 含み益+100%で半分利確
    - ルール3: レバETF特別
    """
    sym_key = holding["symbol"]
    sym = SYMBOLS.get(sym_key, {})
    account_key = holding["account"]
    account = ACCOUNTS.get(account_key, {})
    tax_free = account.get("tax_free", False)
    is_leveraged = sym.get("is_leveraged", False)

    # 含み益率を概算
    current_price = _current_price(sym_key, watchlist, geopolitical, sp500_price)
    buy_price = holding.get("proxy_price_at_buy")
    if current_price and buy_price:
        profit_pct = ((current_price - buy_price) / buy_price) * 100
    else:
        profit_pct = None

    decision = "HOLD"
    action = "保有継続"
    reason = ""
    sell_ratio = 0

    # --- ルール3: レバETF ---
    if is_leveraged and profit_pct is not None:
        if profit_pct >= 100:
            decision = "SELL_ALL"
            sell_ratio = 100
            action = f"全部利確（レバレッジETFの減衰リスク回避）"
            reason = f"レバETFで+{profit_pct:.0f}%。長期保有は減衰するので全利確"
        elif profit_pct >= 50:
            decision = "SELL_HALF"
            sell_ratio = 50
            action = f"半分利確（レバETF特別ルール）"
            reason = f"レバETFで+{profit_pct:.0f}%。半分利確して元本回収"
        # 横ばい30日の判定は過去データが必要なのでここでは省略（将来対応）

    # --- ルール2: 含み益+100%到達 ---
    if decision == "HOLD" and profit_pct is not None and profit_pct >= 100:
        decision = "SELL_HALF"
        sell_ratio = 50
        action = "半分利確（ダブル到達）"
        reason = f"含み益+{profit_pct:.0f}%達成。半分利確してタダ株化"

    # --- ルール1: マクロ過熱×含み益 ---
    if decision == "HOLD" and profit_pct is not None:
        met = macro["met_count"]
        # 閾値（NISA/特定口座で差）
        if tax_free:
            # NISA: 含み益+30%以上
            profit_threshold = 30
        else:
            # 特定口座: 含み益+50%以上
            profit_threshold = 50

        if profit_pct >= profit_threshold:
            if met >= 5:
                decision = "SELL_70"
                sell_ratio = 70
                action = "70%利確（5条件フル成立）"
                reason = f"マクロ過熱5/5+含み益{profit_pct:.0f}%。大半を利確"
            elif met >= 4:
                decision = "SELL_50"
                sell_ratio = 50
                action = "50%利確"
                reason = f"マクロ過熱4/5+含み益{profit_pct:.0f}%。半分利確"
            elif met >= 3:
                decision = "SELL_30"
                sell_ratio = 30
                action = "30%利確"
                reason = f"マクロ過熱3/5+含み益{profit_pct:.0f}%。一部利確"
            elif met >= 2:
                decision = "WATCH"
                action = "利確準備"
                reason = f"マクロ過熱2/5。さらに条件揃えば利確。売り注文の準備を"

    # HOLD時の表示
    if decision == "HOLD":
        if profit_pct is not None:
            reason = f"含み益{profit_pct:+.0f}%。マクロ過熱{macro['met_count']}/5。売る必要なし"
        else:
            reason = f"マクロ過熱{macro['met_count']}/5。売る必要なし（価格データなし）"

    # 税金目安（特定口座のみ）
    tax_note = None
    if not tax_free and profit_pct is not None and profit_pct > 0 and sell_ratio > 0:
        profit_amount = holding["invested_amount"] * (profit_pct / 100) * (sell_ratio / 100)
        tax_amount = profit_amount * 0.20315
        tax_note = f"（売却益の約20%が税金。{int(tax_amount):,}円）"

    return {
        "slot": holding.get("slot"),
        "symbol_key": sym_key,
        "symbol_name": sym.get("name", sym_key),
        "short_name": sym.get("short_name", sym_key),
        "account_label": account.get("label", account_key),
        "broker": sym.get("broker", ""),
        "invested_amount": holding["invested_amount"],
        "invested_date": holding.get("invested_date"),
        "current_price": current_price,
        "buy_price": buy_price,
        "profit_pct": round(profit_pct, 1) if profit_pct is not None else None,
        "estimated_value": int(holding["invested_amount"] * (1 + profit_pct / 100)) if profit_pct is not None else None,
        "estimated_profit": int(holding["invested_amount"] * (profit_pct / 100)) if profit_pct is not None else None,
        "is_leveraged": is_leveraged,
        "tax_free": tax_free,
        "decision": decision,
        "sell_ratio": sell_ratio,
        "action": action,
        "reason": reason,
        "tax_note": tax_note,
    }


def build_portfolio_summary(macro, watchlist, geopolitical, sp500_price, rsi):
    """保有ポートフォリオ全体の集計+銘柄ごとの売り判定"""
    holdings = []
    account_totals = {"nisa_growth": 0, "tokutei": 0}
    for h in PORTFOLIO:
        judged = evaluate_holding_sell(h, macro, watchlist, geopolitical, sp500_price, rsi)
        holdings.append(judged)
        if h["account"] in account_totals:
            account_totals[h["account"]] += h["invested_amount"]

    # 口座枠別の残額
    account_summary = {}
    for acc_key in ["nisa_growth", "tokutei"]:
        acc = ACCOUNTS[acc_key]
        used = account_totals.get(acc_key, 0)
        remaining = acc["annual_limit"] - used
        account_summary[acc_key] = {
            "label": acc["label"],
            "broker": acc["broker"],
            "total": acc["annual_limit"],
            "used": used,
            "remaining": remaining,
            "tax_free": acc["tax_free"],
            "holdings": [h for h in holdings if h["account_label"] == acc["label"]],
        }

    return {
        "accounts": account_summary,
        "holdings": holdings,
        "total_invested": sum(account_totals.values()),
        "total_current_value": sum(h["estimated_value"] for h in holdings if h["estimated_value"]),
        "total_profit": sum(h["estimated_profit"] for h in holdings if h["estimated_profit"]),
    }


# ============================================================
# 投入計画の発動判定
# ============================================================
def evaluate_plan_condition(plan_item, crash_score, sp500_from_high, gold_from_high,
                             nvda_from_high, soxl_price, wti_price, bottom_signals_met):
    """計画条件が満たされているかを判定し、進捗を返す"""
    cond = plan_item["condition"]
    ctype = cond["type"]
    cval = cond["value"]

    met = False
    progress_text = ""

    if ctype == "sp500_from_high":
        if sp500_from_high is not None:
            met = sp500_from_high <= cval
            diff = sp500_from_high - cval  # 負の数同士。mustはcval=-10でsp500=-2なら、-2 - (-10) = +8 (まだ8%足りない)
            progress_text = f"現在{sp500_from_high:+.1f}% / 目標{cval}% → あと{diff:+.1f}%"
        else:
            progress_text = "S&P500データなし"
    elif ctype == "gold_from_high":
        if gold_from_high is not None:
            met = gold_from_high <= cval
            diff = gold_from_high - cval
            progress_text = f"現在{gold_from_high:+.1f}% / 目標{cval}% → あと{diff:+.1f}%"
        elif crash_score is not None and crash_score <= 30:
            met = True
            progress_text = f"Crash Score {crash_score:.0f} ≤ 30 で発動"
        else:
            progress_text = "金データなし"
    elif ctype == "nvda_from_high":
        if nvda_from_high is not None:
            met = nvda_from_high <= cval
            diff = nvda_from_high - cval
            progress_text = f"現在{nvda_from_high:+.1f}% / 目標{cval}% → あと{diff:+.1f}%"
        else:
            progress_text = "NVIDIAデータなし"
    elif ctype == "soxl_and_crash":
        soxl_max = cval["soxl_max"]
        crash_max = cval["crash_max"]
        soxl_ok = soxl_price is not None and soxl_price <= soxl_max
        crash_ok = crash_score is not None and crash_score <= crash_max
        met = soxl_ok and crash_ok
        soxl_str = f"${soxl_price:.2f}" if soxl_price else "N/A"
        crash_str = f"{crash_score:.0f}" if crash_score is not None else "N/A"
        progress_text = f"SOXL {soxl_str}/${soxl_max} + Crash {crash_str}/{crash_max}"
    elif ctype == "wti_price_above":
        met = wti_price is not None and wti_price >= cval
        progress_text = f"WTI現在${wti_price if wti_price else 'N/A'} / 目標${cval}超"
    elif ctype == "bottom_signals":
        met = bottom_signals_met >= cval
        progress_text = f"底打ちシグナル{bottom_signals_met}/7 / 目標{cval}以上"

    return {"met": met, "progress_text": progress_text}


def build_action_list(macro, portfolio_summary, buyback_summary, crash_score, indicators,
                       watchlist, geopolitical, bottom_signals_met):
    """今日やることの優先順リスト"""
    sp500_price = indicators.get("ma_deviation", {}).get("price")
    sp500_high = sp500_price * 1.02 if sp500_price else None  # TODO: 動的取得
    # SPY高値はdata_fetcher側で取得している想定。とりあえず現在値の+2%を仮置き→あとで差し替え

    sp500_from_high = None
    if sp500_price and sp500_high and sp500_high > 0:
        sp500_from_high = ((sp500_price - sp500_high) / sp500_high) * 100

    nvda_data = watchlist.get("NVDA", {})
    nvda_from_high = nvda_data.get("drawdown_pct")

    soxl_price = watchlist.get("SOXL", {}).get("price")
    wti_price = geopolitical.get("wti", {}).get("value")
    gold_price = geopolitical.get("gold", {}).get("value")
    gld_data = watchlist.get("GLD", {})
    gold_from_high = gld_data.get("drawdown_pct")

    actions = []

    # === 1. 売り（優先表示）===
    for h in portfolio_summary["holdings"]:
        if h["decision"] in ("SELL_30", "SELL_50", "SELL_70", "SELL_HALF", "SELL_ALL"):
            urgency = "high" if h["decision"] in ("SELL_70", "SELL_ALL") else "medium"
            actions.append({
                "type": "sell",
                "urgency": urgency,
                "title": f"【売り】{h['short_name']}を{h['sell_ratio']}%利確",
                "symbol_key": h["symbol_key"],
                "symbol_name": h["symbol_name"],
                "account": h["account_label"],
                "broker": h["broker"],
                "amount_text": f"保有{h['invested_amount']:,}円 × {h['sell_ratio']}%",
                "condition_text": h["reason"],
                "ready": True,
                "tax_note": h.get("tax_note"),
                "detail": h["action"],
            })
        elif h["decision"] == "WATCH":
            actions.append({
                "type": "watch",
                "urgency": "low",
                "title": f"【利確準備】{h['short_name']}",
                "symbol_key": h["symbol_key"],
                "symbol_name": h["symbol_name"],
                "account": h["account_label"],
                "broker": h["broker"],
                "condition_text": h["reason"],
                "ready": False,
                "detail": h["action"],
            })

    # === 1.5 買い戻し（利確した資金の再投入予約・優先度高）===
    for bb in buyback_summary.get("active_actions", []):
        actions.append({
            "type": "buyback",
            "urgency": bb.get("urgency", "medium"),
            "title": f"【買い戻し】{bb['short_name']} を{bb['amount_text']}（{bb['stage_label']}）",
            "symbol_key": bb.get("entry_id"),
            "symbol_name": bb["symbol_name"],
            "short_name": bb["short_name"],
            "account": bb["account"],
            "broker": bb["broker"],
            "broker_section": bb["broker_section"],
            "search_keyword": bb["search_keyword"],
            "order_method": bb["order_method"],
            "amount": bb["amount"],
            "amount_text": bb["amount_text"],
            "condition_text": bb["condition_text"],
            "ready": True,
            "detail": f"{bb.get('original_reason', '')}（{bb.get('sold_date', '')}利確分）",
        })

    # === 2. 買い（計画）===
    for plan in PLAN:
        sym = SYMBOLS.get(plan["symbol"], {})
        acc = ACCOUNTS.get(plan["account"], {})
        result = evaluate_plan_condition(
            plan, crash_score, sp500_from_high, gold_from_high,
            nvda_from_high, soxl_price, wti_price, bottom_signals_met,
        )

        urgency = "medium" if result["met"] else "none"
        action_type = "buy" if result["met"] else "buy_wait"

        actions.append({
            "type": action_type,
            "urgency": urgency,
            "title": ("【買い発動】" if result["met"] else "【買い待機】")
                     + f"{acc.get('label', plan['account'])} {plan['label']}",
            "symbol_key": plan["symbol"],
            "symbol_name": sym.get("name", plan["symbol"]),
            "short_name": sym.get("short_name", plan["symbol"]),
            "ticker_display": sym.get("ticker_display", ""),
            "account": acc.get("label", plan["account"]),
            "broker": sym.get("broker", ""),
            "broker_section": sym.get("broker_section", ""),
            "search_keyword": sym.get("search_keyword", ""),
            "order_method": sym.get("order_method", ""),
            "settlement_days": sym.get("settlement_days", 2),
            "amount": plan["amount"],
            "amount_text": f"{plan['amount']:,}円",
            "condition_text": plan["condition_text"],
            "progress_text": result["progress_text"],
            "ready": result["met"],
            "priority": plan["priority"],
            "slot": plan["slot"],
            "is_leveraged": sym.get("is_leveraged", False),
        })

    # === 並び替え（緊急度 > ready > priority）===
    urgency_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    actions.sort(key=lambda a: (
        urgency_order.get(a["urgency"], 3),
        0 if a.get("ready") else 1,
        a.get("priority", 99),
    ))

    return actions


# ============================================================
# セクター別情報（参考表示用。既存ロジックを簡略化して維持）
# ============================================================
def evaluate_sector_info(wti, xle_data, nvda_data, soxl_data, gold_price, gld_data,
                         crash_score, sp500_price, sp500_high):
    """セクター別の参考情報（買いシグナルは action_list で出すので、ここは状況説明のみ）"""
    xle_price = xle_data.get("price")
    xle_from_high = xle_data.get("drawdown_pct", 0)
    nvda_price = nvda_data.get("price")
    nvda_from_high = nvda_data.get("drawdown_pct", 0)
    soxl_price = soxl_data.get("price")
    gld_price = gld_data.get("price")
    gld_from_high = gld_data.get("drawdown_pct", 0)

    return {
        "energy": {
            "label": "エネルギー",
            "status": f"XLE ${xle_price} (高値比{xle_from_high:+.1f}%) / WTI ${wti if wti else 'N/A'}",
            "comment": _energy_comment(wti, xle_from_high),
        },
        "semiconductor": {
            "label": "半導体",
            "status": f"NVDA ${nvda_price} (高値比{nvda_from_high:+.1f}%) / SOXL ${soxl_price if soxl_price else 'N/A'}",
            "comment": _semi_comment(nvda_from_high, soxl_price, crash_score),
        },
        "broad_market": {
            "label": "広域市場（S&P500）",
            "status": f"S&P500 {sp500_price:.0f}" if sp500_price else "S&P500 N/A" ,
            "comment": _broad_comment(crash_score, sp500_price, sp500_high),
        },
        "gold": {
            "label": "ゴールド",
            "status": f"GLD ${gld_price if gld_price else 'N/A'} (高値比{gld_from_high:+.1f}%) / 金 ${gold_price if gold_price else 'N/A'}",
            "comment": _gold_comment(gld_from_high, crash_score),
        },
    }


def _energy_comment(wti, xle_from_high):
    if wti is None:
        return "原油データ取得失敗"
    if wti <= 80:
        return "停戦後のバーゲン価格。XLEを買う好機"
    if wti <= 90:
        return "調整中。この水準なら買い検討"
    if xle_from_high and xle_from_high <= -20:
        return "XLEが大幅下落。買い時"
    if wti >= 120:
        return "原油高騰中。高値掴みリスク高い"
    return "中途半端な価格帯。原油$90以下まで待ち"


def _semi_comment(nvda_from_high, soxl_price, crash_score):
    if nvda_from_high is None:
        return "NVIDIAデータ取得失敗"
    if nvda_from_high <= -40:
        return "NVIDIAが異常な安値。歴史的買い場"
    if nvda_from_high <= -30:
        return "NVIDIA十分に下落。買い検討圏"
    if soxl_price and soxl_price <= 30 and crash_score and crash_score <= 20:
        return "SOXL+市場恐怖で買い検討圏"
    return "NVIDIAはまだ高値圏。-30%まで待ち"


def _broad_comment(crash_score, sp500_price, sp500_high):
    if crash_score is None:
        return "データ不足"
    if crash_score <= 20:
        return "極度の恐怖。歴史的買い場"
    if crash_score <= 30:
        return "恐怖圏。段階買いのチャンス"
    if crash_score <= 50:
        return "中立圏。急がない"
    return "強欲圏。利確検討"


def _gold_comment(gld_from_high, crash_score):
    if gld_from_high is not None and gld_from_high <= -10:
        return "金が調整中。買い時"
    if crash_score and crash_score <= 30:
        return "市場恐怖+金は安全資産として仕込むタイミング"
    if gld_from_high is not None and gld_from_high >= -3:
        return "金は高値圏。利確検討局面"
    return "様子見"


def evaluate_forex(usdjpy):
    if usdjpy is None:
        return None
    if usdjpy >= 160:
        return {"usdjpy": usdjpy, "risk_level": "HIGH",
                "note": "日銀介入警戒ライン",
                "opportunity": "介入で円高 → 米国株の円建て価格が下がる → 買い場"}
    if usdjpy >= 155:
        return {"usdjpy": usdjpy, "risk_level": "MEDIUM",
                "note": "円安圏。分割投入推奨",
                "opportunity": "分割投入で為替リスクを時間分散"}
    if usdjpy >= 145:
        return {"usdjpy": usdjpy, "risk_level": "LOW",
                "note": "適度な円安",
                "opportunity": "米国株投資に良好な環境"}
    return {"usdjpy": usdjpy, "risk_level": "FAVORABLE",
            "note": "円高水準",
            "opportunity": "ドル建て資産が割安"}


# ============================================================
# 統合（generate_advice）
# ============================================================
def generate_advice(crash_score, indicators, watchlist, geopolitical, bottom_signals=None):
    """メインエントリー: ダッシュボード用の完全な advice を返す"""
    # 基礎データ
    fear_greed = indicators.get("fear_greed", {}).get("value")
    vix = indicators.get("vix", {}).get("value")
    rsi = indicators.get("rsi", {}).get("value")
    ma_data = indicators.get("ma_deviation", {})
    sp500_price = ma_data.get("price")
    sp500_high = ma_data.get("high_52w")  # data_fetcher側で対応していれば使う
    if not sp500_high:
        # フォールバック: MA200日線から概算
        ma200 = ma_data.get("ma200")
        sp500_high = ma200 * 1.15 if ma200 else (sp500_price * 1.05 if sp500_price else None)
    usdjpy = geopolitical.get("usdjpy", {}).get("value")
    wti = geopolitical.get("wti", {}).get("value")
    gold_price = geopolitical.get("gold", {}).get("value")

    xle_data = watchlist.get("XLE", {})
    nvda_data = watchlist.get("NVDA", {})
    soxl_data = watchlist.get("SOXL", {})
    gld_data = watchlist.get("GLD", {})

    # マクロシグナル
    macro = evaluate_macro_signals(crash_score, fear_greed, vix, rsi, sp500_price, sp500_high)

    # ポートフォリオ
    portfolio = build_portfolio_summary(macro, watchlist, geopolitical, sp500_price, rsi)

    # 底打ちシグナル成立数
    bottom_met = 0
    if bottom_signals and isinstance(bottom_signals, dict):
        bottom_met = bottom_signals.get("met_count", 0)

    # 買い戻しキュー
    buyback = build_buyback_summary(crash_score, bottom_met)

    # つみたて枠の警告（マクロ5/5フル成立時のみ）
    tsumitate_warning = evaluate_tsumitate_warning(macro)

    # アクションリスト
    action_list = build_action_list(macro, portfolio, buyback, crash_score, indicators,
                                      watchlist, geopolitical, bottom_met)

    # セクター状況（参考）
    sectors_info = evaluate_sector_info(wti, xle_data, nvda_data, soxl_data,
                                          gold_price, gld_data, crash_score,
                                          sp500_price, sp500_high)

    # 為替
    forex = evaluate_forex(usdjpy)

    # ヘッドライン生成
    headline = _build_headline(action_list, macro, portfolio)

    # サマリー
    ready_buys = sum(1 for a in action_list if a["type"] == "buy" and a.get("ready"))
    active_sells = sum(1 for a in action_list if a["type"] == "sell")
    if active_sells > 0:
        summary = f"売りシグナル{active_sells}件発動中。利確を検討してください"
    elif ready_buys > 0:
        summary = f"買い発動{ready_buys}件。注文準備を"
    elif macro["met_count"] >= 2:
        summary = f"マクロ過熱{macro['met_count']}/5。利確準備を始めるタイミング"
    else:
        summary = "全件待機中。条件到達まで待ちましょう"

    return {
        "headline": headline,
        "summary": summary,
        "action_list": action_list,
        "portfolio": portfolio,
        "buyback": buyback,
        "tsumitate_warning": tsumitate_warning,
        "macro_signals": macro,
        "sectors": sectors_info,
        "forex": forex,
        "bottom_note": _bottom_note(bottom_signals),
        "updated_at": datetime.now().isoformat(),
        "symbols": SYMBOLS,
        "accounts": ACCOUNTS,
    }


def _build_headline(action_list, macro, portfolio):
    """最優先アクションをヘッドラインに"""
    if not action_list:
        return "条件待機中。今日は動かなくて大丈夫です"

    top = action_list[0]
    if top["type"] == "sell":
        return f"【売り】{top['short_name'] if 'short_name' in top else top['symbol_name']}を{top.get('amount_text', '')}利確"
    if top["type"] == "buy":
        return f"【買い発動】{top['account']} {top.get('short_name', '')}を{top['amount_text']}注文"
    if top["type"] == "buy_wait":
        # 買い待機の中で一番進捗の良いものを返す
        return f"今日は動かなくて大丈夫。次の1手: {top['account']} {top.get('short_name', '')}（{top['progress_text']}）"
    if top["type"] == "watch":
        return f"利確準備: {top.get('short_name', '')}の売り注文を用意"
    return "条件待機中"


def _bottom_note(bottom_signals):
    if not bottom_signals:
        return None
    met = bottom_signals.get("met_count", 0)
    total = bottom_signals.get("total_conditions", 7)
    if met >= 5:
        return f"底打ちシグナル {met}/{total} 成立。残り全額投入を強く推奨"
    if met >= 3:
        return f"底打ちシグナル {met}/{total} 成立。買い場が近い"
    if bottom_signals.get("selling_climax"):
        return "セリングクライマックス検出。歴史的買い場の可能性"
    return None


# ============================================================
# 後方互換: 旧コードからの参照用（段階的に削除）
# ============================================================
STRATEGY = {
    "total_budget": 2970000,
    "nisa_growth_budget": ACCOUNTS["nisa_growth"]["annual_limit"],
    "nisa_tsumitate_budget": ACCOUNTS["nisa_tsumitate"]["annual_limit"],
    "tokutei_budget": ACCOUNTS["tokutei"]["annual_limit"],
    "brokers": {"nisa": "SBI証券（新NISA）", "tokutei": "楽天証券（特定口座）"},
    "notes": "つみたて投資枠120万は個人で自動積立（ツール対象外）。管理対象は成長投資枠+特定口座の297万",
    # 旧UIが参照する tranches を生成（done=PORTFOLIO、pending=PLAN）
    "tranches": [
        *[
            {
                "label": h.get("note", "投入済み"),
                "amount": h["invested_amount"],
                "account": "nisa" if h["account"] == "nisa_growth" else "tokutei",
                "status": "done",
                "date": h.get("invested_date"),
                "ticker": SYMBOLS.get(h["symbol"], {}).get("short_name", h["symbol"]),
            }
            for h in PORTFOLIO
        ],
        *[
            {
                "label": p["label"],
                "amount": p["amount"],
                "account": "nisa" if p["account"] == "nisa_growth" else "tokutei",
                "status": "pending",
                "ticker": SYMBOLS.get(p["symbol"], {}).get("short_name", p["symbol"]),
                "condition": p["condition_text"],
            }
            for p in PLAN
        ],
    ],
}

SETTLEMENT_LAG = {
    key: {"name": sym["name"], "days": sym["settlement_days"], "note": sym.get("note", "")}
    for key, sym in SYMBOLS.items()
}
