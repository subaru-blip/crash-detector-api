"""
Budget Tracker - 投入履歴管理
清水さんの資金（297万）の投入状況を追跡する
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "budget.db"

INITIAL_BUDGET = {
    "nisa": 2400000,     # NISA成長枠 240万
    "tokutei": 570000,   # 特定口座 57万
}


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL,
            amount INTEGER NOT NULL,
            target TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def get_budget_status() -> dict:
    """現在の資金状況を返す"""
    conn = get_db()
    rows = conn.execute(
        "SELECT account, SUM(amount) FROM investments GROUP BY account"
    ).fetchall()
    conn.close()

    invested = {r[0]: r[1] for r in rows}
    nisa_used = invested.get("nisa", 0)
    tokutei_used = invested.get("tokutei", 0)

    return {
        "nisa": {
            "total": INITIAL_BUDGET["nisa"],
            "invested": nisa_used,
            "remaining": INITIAL_BUDGET["nisa"] - nisa_used,
            "label": "NISA成長枠",
        },
        "tokutei": {
            "total": INITIAL_BUDGET["tokutei"],
            "invested": tokutei_used,
            "remaining": INITIAL_BUDGET["tokutei"] - tokutei_used,
            "label": "特定口座",
        },
        "total_remaining": (INITIAL_BUDGET["nisa"] - nisa_used) + (INITIAL_BUDGET["tokutei"] - tokutei_used),
        "total_invested": nisa_used + tokutei_used,
    }


def record_investment(account: str, amount: int, target: str, note: str = "") -> dict:
    """投入を記録する"""
    if account not in INITIAL_BUDGET:
        return {"error": f"口座は nisa または tokutei を指定してください"}
    if amount <= 0:
        return {"error": "金額は0より大きい値を入れてください"}

    # 残額チェック
    status = get_budget_status()
    remaining = status[account]["remaining"]
    if amount > remaining:
        return {"error": f"{status[account]['label']}の残額は{remaining:,}円です。{amount:,}円は入れられません"}

    conn = get_db()
    conn.execute(
        "INSERT INTO investments (account, amount, target, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (account, amount, target, note, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    new_status = get_budget_status()
    return {
        "success": True,
        "message": f"{new_status[account]['label']}に{amount:,}円（{target}）を記録しました",
        "budget": new_status,
    }


def get_investment_history() -> dict:
    """投入履歴を返す"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, account, amount, target, note, created_at FROM investments ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    history = []
    for r in rows:
        account_label = "NISA成長枠" if r[1] == "nisa" else "特定口座"
        history.append({
            "id": r[0],
            "account": r[1],
            "account_label": account_label,
            "amount": r[2],
            "amount_label": f"{r[2]:,}円",
            "target": r[3],
            "note": r[4],
            "date": r[5],
        })

    return {"history": history, "count": len(history)}
