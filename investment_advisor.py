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

import state_tracker


# ============================================================
# ヒステリシス設定
# ============================================================
# 閾値境界で判定が揺れる問題を解消するためのバッファ。
# - 下抜け型（from_high など）: 発動閾値 + buffer（％ポイント戻る）で解除
# - 上抜け型（wti_price_above）: 発動閾値 − buffer（価格下がる）で解除
# - 複合条件（gold_and_crash 等）: 両方が buffer 分戻ったら解除
HYSTERESIS_BUFFER = {
    "sp500_from_high": 3,     # 発動-10% → 解除-7%
    "gold_from_high": 3,      # 発動-10% → 解除-7%
    "nvda_from_high": 5,      # 発動-20% → 解除-15%（高ボラ）
    "wti_price_above": 5,     # 発動$120 → 解除$115
    "wti_price_below": 5,     # 発動$90以下 → 解除$95
    "bottom_signals": 1,      # 発動3/7 → 解除2/7
    "gold_and_crash": {"gold_from_high": 3, "crash_max": 5},
    "soxl_and_crash": {"soxl_max": 3, "crash_max": 5},
    # OR条件（どちらか発動 → 両方とも解除閾値に戻るまで active 継続）
    "sp500_or_bottom": {"sp500_from_high": 3, "bottom_signals": 1},
    "bottom_or_wti": {"bottom_signals": 1, "wti_price_below": 5},
}

# 発動後この営業日数は「強制継続」する（intraday の戻りで消えないロック期間）
# 清水さんの注文サイクル（昼・夜）に合わせ、最低でも3営業日は買い表示を維持する。
# これで「深夜に瞬間的に閾値タッチ → 起きた時には消えている」問題を根本解消。
HOLD_BUSINESS_DAYS = 3


def _business_days_since(triggered_at_iso: str) -> int:
    """triggered_at から今日までの営業日数（土日除く、発動日は含めない）"""
    if not triggered_at_iso:
        return 999
    try:
        s = datetime.fromisoformat(triggered_at_iso).date()
    except Exception:
        return 999
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    if today <= s:
        return 0
    count = 0
    d = s
    while d < today:
        d = d + _td(days=1)
        if d.weekday() < 5:  # 0-4 = 月-金
            count += 1
    return count


def _build_close_snapshot(daily_closes: dict, watchlist: dict) -> dict:
    """日足終値から判定用スナップショットを作る。
    intraday の瞬間値ではなく「直近の日足終値」で発動判定するため。

    Render 無料枠で signal_state.db が消えても、終値ベースで再判定すれば
    「発動しているべき状態」は自動復元される副次効果もある。
    """
    if not daily_closes:
        return {}

    def latest_close(ticker):
        items = daily_closes.get(ticker, [])
        return items[-1]["close"] if items else None

    snapshot = {}
    spy_close = latest_close("SPY")
    gld_close = latest_close("GLD")
    nvda_close = latest_close("NVDA")
    soxl_close = latest_close("SOXL")
    wti_close = latest_close("CL=F")

    spy_high = watchlist.get("SPY", {}).get("high_52w")
    gld_high = watchlist.get("GLD", {}).get("high_52w")
    nvda_high = watchlist.get("NVDA", {}).get("high_52w")

    if spy_close and spy_high and spy_high > 0:
        snapshot["sp500_from_high"] = ((spy_close - spy_high) / spy_high) * 100
    if gld_close and gld_high and gld_high > 0:
        snapshot["gold_from_high"] = ((gld_close - gld_high) / gld_high) * 100
    if nvda_close and nvda_high and nvda_high > 0:
        snapshot["nvda_from_high"] = ((nvda_close - nvda_high) / nvda_high) * 100
    if soxl_close is not None:
        snapshot["soxl_price"] = soxl_close
    if wti_close is not None:
        snapshot["wti_price"] = wti_close
    return snapshot


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
        "broker": "SBI証券",
        "broker_section": "外国株式 > 米国株式 > ETF検索",
        "search_keyword": "GDX",
        "order_method": "株数指定（ドル建て・円貨決済）",
        "settlement_days": 3,
        "category": "金鉱株",
        "is_leveraged": False,
        "note": "金鉱会社ETF。金価格上昇時にゴールド本体より大きく動く。NISA成長枠で運用（2026-04-22方針変更）",
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
# 設計方針（清水さんの「S&P500以外の成長株は慎重に」方針を反映・2026-04-22）:
# - S&P500を最優先の買い対象に（NISA成長枠の2/3）
# - 個別株・セクターETFは「打診買い→本格買い」の2段階
# - 集中リスクを減らすため各ポジションは小ロット
PLAN = [
    # ===== NISA成長枠（残180万） =====
    {
        "slot": "nisa_sp500_2", "account": "nisa_growth", "symbol": "emaxis_sp500",
        "amount": 600000, "label": "2回目投入（S&P500）", "priority": 1,
        "condition": {"type": "sp500_from_high", "value": -10},
        "condition_text": "S&P500（SPY）が高値から-10%以下まで下落",
        "stage": "main",
    },
    {
        "slot": "nisa_sp500_3", "account": "nisa_growth", "symbol": "emaxis_sp500",
        "amount": 600000, "label": "3回目投入（S&P500）", "priority": 2,
        "condition": {"type": "sp500_or_bottom",
                      "value": {"sp500_from_high": -15, "bottom_signals": 3}},
        "condition_text": "S&P500（SPY）が高値から-15%以下 or 底打ち3/7以上",
        "stage": "main",
    },
    # nisa_gold_probe: 2026-04-22 実行済（PORTFOLIO に移管）
    {
        "slot": "nisa_gold_main", "account": "nisa_growth", "symbol": "gld_nisa",
        "amount": 200000, "label": "ゴールド本格買い", "priority": 3,
        "condition": {"type": "gold_and_crash", "value": {"gold_from_high": -15, "crash_max": 30}},
        "condition_text": "金が高値から-15% かつ Crash Score 30以下",
        "stage": "main",
    },
    # nisa_gdx: 2026-04-24 実行済（PORTFOLIO に移管）
    {
        "slot": "nisa_reserve", "account": "nisa_growth", "symbol": "emaxis_sp500",
        "amount": 200000, "label": "予備枠（S&P500 or 状況に応じて切替）", "priority": 5,
        "condition": {"type": "bottom_or_wti",
                      "value": {"bottom_signals": 3, "wti_price_below": 90}},
        "condition_text": "底打ちシグナル3/7以上 or エネルギー急落（WTI $90以下）",
        "stage": "reserve",
    },

    # ===== 特定口座（残47万・GDXをNISAに移動済） =====
    {
        "slot": "tokutei_nvda_probe", "account": "tokutei", "symbol": "nvda",
        "amount": 120000, "label": "NVIDIA打診買い", "priority": 1,
        "condition": {"type": "nvda_from_high", "value": -20},
        "condition_text": "NVIDIAが高値から-20%以下（打診買い・小ロット）",
        "stage": "probe",
    },
    {
        "slot": "tokutei_nvda_main", "account": "tokutei", "symbol": "nvda",
        "amount": 120000, "label": "NVIDIA本格買い", "priority": 2,
        "condition": {"type": "nvda_from_high", "value": -30},
        "condition_text": "NVIDIAが高値から-30%以下（本格買い）",
        "stage": "main",
    },
    {
        "slot": "tokutei_soxl", "account": "tokutei", "symbol": "soxl",
        "amount": 140000, "label": "SOXL（一発狙い）", "priority": 3,
        "condition": {"type": "soxl_and_crash", "value": {"soxl_max": 30, "crash_max": 20}},
        "condition_text": "SOXL $30以下 かつ Crash Score 20以下",
        "stage": "main",
    },
    {
        "slot": "tokutei_xom", "account": "tokutei", "symbol": "xom",
        "amount": 90000, "label": "XOM（エネルギー個別）", "priority": 4,
        "condition": {"type": "wti_price_above", "value": 120},
        "condition_text": "WTI原油 $120超で封鎖長期化確認時",
        "stage": "main",
    },
    {
        "slot": "tokutei_free_reserve", "account": "tokutei", "symbol": "nvda",
        "amount": 100000, "label": "フリー予備枠（状況判断・楽天証券）", "priority": 5,
        "condition": {"type": "manual", "value": None},
        "condition_text": "清水さんの判断で任意発動（相場状況・新規機会に柔軟対応）",
        "stage": "free",
        "note": "2026-04-22 追加。GDXをNISAに移した分の10万を特定口座に戻した枠。"
                "半導体押し目・SMH・AVGO等、状況に応じて使う。"
                "※ TSM(台湾セミコン)は2027年台湾有事リスクのため避ける方針",
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
        "note": "1回目投入（S&P500・NISA成長枠）",
    },
    {
        "slot": "nisa_gold_probe_20260422",
        "symbol": "gld_nisa",
        "account": "nisa_growth",
        "invested_amount": 100000,          # 打診買い枠として10万計上（実約定 240口×¥405.30≈¥97,272）
        "invested_date": "2026-04-22",
        "proxy_price_at_buy": 429.57,       # 購入日のGLD価格（proxy_ticker）
        "shares": 240,                      # 実際の購入口数
        "actual_price_jpy": 405.30,         # 実際の約定価格（参考値・成行のため要アップデート）
        "note": "ゴールド打診買い・NISA成長枠（425A 240口成行・SBI証券）",
    },
    {
        "slot": "nisa_gdx_20260424",
        "symbol": "gdx",
        "account": "nisa_growth",
        "invested_amount": 100000,          # 打診買い枠として10万計上（実受渡¥103,632・円貨決済）
        "invested_date": "2026-04-24",
        "proxy_price_at_buy": 92.50,        # GDX約定価格（$）
        "shares": 7,                        # 約定株数
        "actual_price_usd": 92.50,          # 指値約定
        "actual_jpy_settlement": 103632,    # 円貨決済額（SBI精算予定: 04/28出金振替）
        "fx_at_buy": 159.80,                # 約定時の米ドル/円レート（参考）
        "note": "GDX打診買い・NISA成長枠（7株×$92.50指値・SBI証券・円貨決済）",
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
def _evaluate_raw_condition(ctype, cval, crash_score, sp500_from_high, gold_from_high,
                             nvda_from_high, soxl_price, wti_price, bottom_signals_met):
    """バッファ無しの素の条件を評価。True=発動閾値到達"""
    if ctype == "sp500_from_high":
        return sp500_from_high is not None and sp500_from_high <= cval
    if ctype == "gold_from_high":
        return gold_from_high is not None and gold_from_high <= cval
    if ctype == "nvda_from_high":
        return nvda_from_high is not None and nvda_from_high <= cval
    if ctype == "wti_price_above":
        return wti_price is not None and wti_price >= cval
    if ctype == "wti_price_below":
        return wti_price is not None and wti_price <= cval
    if ctype == "bottom_signals":
        return bottom_signals_met >= cval
    if ctype == "gold_and_crash":
        g = cval.get("gold_from_high", -15)
        c = cval.get("crash_max", 30)
        gold_ok = gold_from_high is not None and gold_from_high <= g
        crash_ok = crash_score is not None and crash_score <= c
        return gold_ok and crash_ok
    if ctype == "soxl_and_crash":
        soxl_ok = soxl_price is not None and soxl_price <= cval["soxl_max"]
        crash_ok = crash_score is not None and crash_score <= cval["crash_max"]
        return soxl_ok and crash_ok
    if ctype == "sp500_or_bottom":
        sp = cval.get("sp500_from_high", -15)
        bs = cval.get("bottom_signals", 3)
        sp_ok = sp500_from_high is not None and sp500_from_high <= sp
        bs_ok = bottom_signals_met >= bs
        return sp_ok or bs_ok
    if ctype == "bottom_or_wti":
        bs = cval.get("bottom_signals", 3)
        wti_th = cval.get("wti_price_below", 90)
        bs_ok = bottom_signals_met >= bs
        wti_ok = wti_price is not None and wti_price <= wti_th
        return bs_ok or wti_ok
    if ctype == "manual":
        # 清水さんの判断で任意発動する枠。自動では発動しない
        return False
    return False


def _is_release_condition_met(ctype, cval, buffer, crash_score, sp500_from_high,
                               gold_from_high, nvda_from_high, soxl_price, wti_price,
                               bottom_signals_met):
    """解除条件（buffer分だけ戻ったか）を評価。True=解除すべき"""
    if ctype == "sp500_from_high":
        return sp500_from_high is None or sp500_from_high > cval + buffer
    if ctype == "gold_from_high":
        return gold_from_high is None or gold_from_high > cval + buffer
    if ctype == "nvda_from_high":
        return nvda_from_high is None or nvda_from_high > cval + buffer
    if ctype == "wti_price_above":
        return wti_price is None or wti_price < cval - buffer
    if ctype == "wti_price_below":
        return wti_price is None or wti_price > cval + buffer
    if ctype == "bottom_signals":
        return bottom_signals_met < cval - buffer
    if ctype == "gold_and_crash":
        g = cval.get("gold_from_high", -15)
        c = cval.get("crash_max", 30)
        bg = buffer.get("gold_from_high", 3) if isinstance(buffer, dict) else 3
        bc = buffer.get("crash_max", 5) if isinstance(buffer, dict) else 5
        gold_released = gold_from_high is None or gold_from_high > g + bg
        crash_released = crash_score is None or crash_score > c + bc
        return gold_released and crash_released
    if ctype == "soxl_and_crash":
        bs = buffer.get("soxl_max", 3) if isinstance(buffer, dict) else 3
        bc = buffer.get("crash_max", 5) if isinstance(buffer, dict) else 5
        soxl_released = soxl_price is None or soxl_price > cval["soxl_max"] + bs
        crash_released = crash_score is None or crash_score > cval["crash_max"] + bc
        return soxl_released and crash_released
    if ctype == "sp500_or_bottom":
        # OR条件: 両方とも解除閾値に戻ったときのみ解除
        sp = cval.get("sp500_from_high", -15)
        bs = cval.get("bottom_signals", 3)
        b_sp = buffer.get("sp500_from_high", 3) if isinstance(buffer, dict) else 3
        b_bs = buffer.get("bottom_signals", 1) if isinstance(buffer, dict) else 1
        sp_released = sp500_from_high is None or sp500_from_high > sp + b_sp
        bs_released = bottom_signals_met < bs - b_bs
        return sp_released and bs_released
    if ctype == "bottom_or_wti":
        bs = cval.get("bottom_signals", 3)
        wti_th = cval.get("wti_price_below", 90)
        b_bs = buffer.get("bottom_signals", 1) if isinstance(buffer, dict) else 1
        b_wti = buffer.get("wti_price_below", 5) if isinstance(buffer, dict) else 5
        bs_released = bottom_signals_met < bs - b_bs
        wti_released = wti_price is None or wti_price > wti_th + b_wti
        return bs_released and wti_released
    return True


def _build_progress_text(ctype, cval, crash_score, sp500_from_high, gold_from_high,
                          nvda_from_high, soxl_price, wti_price, bottom_signals_met):
    """進捗テキスト（UI表示用）"""
    if ctype == "sp500_from_high":
        if sp500_from_high is not None:
            diff = sp500_from_high - cval
            return f"現在{sp500_from_high:+.1f}% / 目標{cval}% → あと{diff:+.1f}%"
        return "S&P500データなし"
    if ctype == "gold_from_high":
        if gold_from_high is not None:
            diff = gold_from_high - cval
            return f"現在{gold_from_high:+.1f}% / 目標{cval}% → あと{diff:+.1f}%"
        return "金データなし"
    if ctype == "nvda_from_high":
        if nvda_from_high is not None:
            diff = nvda_from_high - cval
            return f"現在{nvda_from_high:+.1f}% / 目標{cval}% → あと{diff:+.1f}%"
        return "NVIDIAデータなし"
    if ctype == "gold_and_crash":
        g = cval.get("gold_from_high", -15)
        c = cval.get("crash_max", 30)
        gold_str = f"{gold_from_high:+.1f}%" if gold_from_high is not None else "N/A"
        crash_str = f"{crash_score:.0f}" if crash_score is not None else "N/A"
        return f"金{gold_str}/目標{g}% + Crash {crash_str}/{c}"
    if ctype == "soxl_and_crash":
        soxl_str = f"${soxl_price:.2f}" if soxl_price else "N/A"
        crash_str = f"{crash_score:.0f}" if crash_score is not None else "N/A"
        return f"SOXL {soxl_str}/${cval['soxl_max']} + Crash {crash_str}/{cval['crash_max']}"
    if ctype == "wti_price_above":
        return f"WTI現在${wti_price if wti_price else 'N/A'} / 目標${cval}超"
    if ctype == "wti_price_below":
        return f"WTI現在${wti_price if wti_price else 'N/A'} / 目標${cval}以下"
    if ctype == "bottom_signals":
        return f"底打ちシグナル{bottom_signals_met}/7 / 目標{cval}以上"
    if ctype == "sp500_or_bottom":
        sp = cval.get("sp500_from_high", -15)
        bs = cval.get("bottom_signals", 3)
        sp_str = f"{sp500_from_high:+.1f}%" if sp500_from_high is not None else "N/A"
        return f"S&P500 {sp_str}/目標{sp}% ｜ 底打ち{bottom_signals_met}/7 目標{bs}以上（OR）"
    if ctype == "bottom_or_wti":
        bs = cval.get("bottom_signals", 3)
        wti_th = cval.get("wti_price_below", 90)
        wti_str = f"${wti_price}" if wti_price else "N/A"
        return f"底打ち{bottom_signals_met}/7 目標{bs}以上 ｜ WTI {wti_str}/目標${wti_th}以下（OR）"
    if ctype == "manual":
        return "清水さんの判断で任意発動（自動トリガーなし）"
    return ""


def evaluate_plan_condition(plan_item, crash_score, sp500_from_high, gold_from_high,
                             nvda_from_high, soxl_price, wti_price, bottom_signals_met,
                             close_snapshot=None, use_hysteresis=True):
    """
    計画条件を判定。終値ベース + 3営業日継続方式（2026-04-24〜）。

    発動:
        - 日足終値ベースの指標で閾値到達（intradayの瞬間値は無視）
        - close_snapshot が無い場合は intraday 値で判定（後方互換）
    継続:
        - 発動後 HOLD_BUSINESS_DAYS 営業日は強制継続（清水さんの注文サイクル対応）
    解除:
        - 保護期間経過 かつ 終値ベースで解除閾値に戻った時のみ

    返却:
        met: 実際に発動状態か（ヒステリシス適用後）
        progress_text: UI表示用の進捗テキスト
        hysteresis_state: 状態表記
            - inactive: 未発動、閾値未達
            - just_fired: 今回の判定で発動（inactive→active・終値ベース）
            - active_hold: 発動中・保護期間内（強制継続・残日数をprogressに表示）
            - active: 発動中・保護期間後（終値で継続中 or 解除閾値未達）
            - released: 解除閾値まで戻って解除（active→inactive）
            - disabled: ヒステリシス無効時
    """
    cond = plan_item["condition"]
    ctype = cond["type"]
    cval = cond["value"]
    key = f"plan:{plan_item.get('slot', ctype)}"

    # intraday 値ベースの進捗テキスト（体感に合わせた表示用）
    progress_text = _build_progress_text(
        ctype, cval, crash_score, sp500_from_high, gold_from_high,
        nvda_from_high, soxl_price, wti_price, bottom_signals_met,
    )
    fired_intraday = _evaluate_raw_condition(
        ctype, cval, crash_score, sp500_from_high, gold_from_high,
        nvda_from_high, soxl_price, wti_price, bottom_signals_met,
    )

    # 終値ベースの指標（発動/解除判定に使う・揺れ防止）
    cs = close_snapshot or {}
    close_sp500_from_high = cs.get("sp500_from_high", sp500_from_high)
    close_gold_from_high = cs.get("gold_from_high", gold_from_high)
    close_nvda_from_high = cs.get("nvda_from_high", nvda_from_high)
    close_soxl_price = cs.get("soxl_price", soxl_price)
    close_wti_price = cs.get("wti_price", wti_price)

    fired_by_close = _evaluate_raw_condition(
        ctype, cval, crash_score, close_sp500_from_high, close_gold_from_high,
        close_nvda_from_high, close_soxl_price, close_wti_price, bottom_signals_met,
    )

    if not use_hysteresis:
        return {"met": fired_intraday, "progress_text": progress_text, "hysteresis_state": "disabled"}

    buffer = HYSTERESIS_BUFFER.get(ctype, 0)
    prev_state = state_tracker.get_signal_state(key)
    state_detail = state_tracker.get_signal_detail(key)

    if prev_state == "active":
        elapsed = _business_days_since(state_detail.get("triggered_at"))
        remaining_hold = max(0, HOLD_BUSINESS_DAYS - elapsed)

        if remaining_hold > 0:
            # 保護期間内 → 無条件継続（intradayが戻っていても維持）
            return {
                "met": True,
                "progress_text": progress_text + f" ※発動中（保護期間 あと{remaining_hold}営業日）",
                "hysteresis_state": "active_hold",
            }

        # 保護期間終了 → 終値ベースで継続/解除を判定
        if fired_by_close:
            return {
                "met": True,
                "progress_text": progress_text + " ※発動継続（終値で閾値継続中）",
                "hysteresis_state": "active",
            }

        released = _is_release_condition_met(
            ctype, cval, buffer, crash_score, close_sp500_from_high, close_gold_from_high,
            close_nvda_from_high, close_soxl_price, close_wti_price, bottom_signals_met,
        )
        if released:
            state_tracker.set_signal_state(key, "inactive")
            return {
                "met": False,
                "progress_text": progress_text + " ※解除閾値まで戻り発動解除（終値ベース）",
                "hysteresis_state": "released",
            }
        return {
            "met": True,
            "progress_text": progress_text + " ※発動継続（解除閾値未達・終値ベース）",
            "hysteresis_state": "active",
        }

    # 未発動 → 終値ベースで発動判定（intradayの瞬間タッチでは発動させない）
    if fired_by_close:
        state_tracker.set_signal_state(key, "active")
        return {
            "met": True,
            "progress_text": progress_text + f" ※今回発動・終値ベース（最低{HOLD_BUSINESS_DAYS}営業日は継続）",
            "hysteresis_state": "just_fired",
        }
    return {
        "met": False,
        "progress_text": progress_text,
        "hysteresis_state": "inactive",
    }


def build_action_list(macro, portfolio_summary, buyback_summary, crash_score, indicators,
                       watchlist, geopolitical, bottom_signals_met, daily_closes=None):
    """今日やることの優先順リスト。
    daily_closes が渡されるとヒステリシス判定が終値ベース＋3営業日継続になる。"""
    close_snapshot = _build_close_snapshot(daily_closes or {}, watchlist)
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
            close_snapshot=close_snapshot,
        )

        urgency = "medium" if result["met"] else "none"
        action_type = "buy" if result["met"] else "buy_wait"
        hysteresis_state = result.get("hysteresis_state", "inactive")

        # タイトル生成（ヒステリシス状態を反映）
        if hysteresis_state == "active":
            title_prefix = "【買い継続】"
        elif hysteresis_state == "just_fired":
            title_prefix = "【買い発動】"
        elif hysteresis_state == "released":
            title_prefix = "【解除】"
        elif result["met"]:
            title_prefix = "【買い発動】"
        else:
            title_prefix = "【買い待機】"

        actions.append({
            "type": action_type,
            "urgency": urgency,
            "title": title_prefix + f"{acc.get('label', plan['account'])} {plan['label']}",
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
            "hysteresis_state": hysteresis_state,
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
def generate_advice(crash_score, indicators, watchlist, geopolitical, bottom_signals=None,
                    daily_closes=None):
    """メインエントリー: ダッシュボード用の完全な advice を返す。
    daily_closes が渡されるとヒステリシスが終値ベース＋3営業日継続で判定される。"""
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
                                      watchlist, geopolitical, bottom_met,
                                      daily_closes=daily_closes)

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
