"""
Signal State Tracker - ヒステリシス用の状態管理

各買い/売り条件（signal_key）の発動状態を SQLite に永続化する。
判定が境界で揺れる問題（例: WTI $89.99=BUY、$90.48=WAIT）を解消するため、
一度 active になったシグナルは「解除閾値」まで戻らないと inactive に戻らない。

状態遷移:
    inactive ── 発動閾値到達 ──▶ active
    active   ── 解除閾値到達 ──▶ inactive

buffer の方向は evaluate 側で決める（下抜け型 vs 上抜け型）。
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# cache.db と統合（data_fetcher と同じDB）
# Render 無料枠のスピンダウン時も維持される。再デプロイ時のみクリアされる。
DB_PATH = Path(__file__).parent / "cache.db"

VALID_STATES = ("active", "inactive")


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_state (
            signal_key TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            triggered_at TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def get_signal_state(signal_key: str) -> str:
    """signal_key の現在状態を返す。登録がなければ 'inactive'。"""
    conn = get_db()
    row = conn.execute(
        "SELECT state FROM signal_state WHERE signal_key = ?",
        (signal_key,),
    ).fetchone()
    conn.close()
    return row[0] if row else "inactive"


def set_signal_state(signal_key: str, state: str) -> None:
    """signal_key の状態を更新する。active 初回遷移時は triggered_at を記録。"""
    if state not in VALID_STATES:
        raise ValueError(f"state must be one of {VALID_STATES}")

    now = datetime.now().isoformat()
    conn = get_db()

    prev = conn.execute(
        "SELECT state, triggered_at FROM signal_state WHERE signal_key = ?",
        (signal_key,),
    ).fetchone()

    if prev is None:
        # 新規登録
        triggered_at = now if state == "active" else None
        conn.execute(
            "INSERT INTO signal_state (signal_key, state, triggered_at, updated_at) VALUES (?, ?, ?, ?)",
            (signal_key, state, triggered_at, now),
        )
    else:
        prev_state, prev_triggered_at = prev
        # inactive → active の時だけ triggered_at を更新
        if state == "active" and prev_state != "active":
            triggered_at = now
        else:
            triggered_at = prev_triggered_at
        conn.execute(
            "UPDATE signal_state SET state = ?, triggered_at = ?, updated_at = ? WHERE signal_key = ?",
            (state, triggered_at, now, signal_key),
        )

    conn.commit()
    conn.close()


def get_signal_detail(signal_key: str) -> dict:
    """state + triggered_at + updated_at をまとめて返す（UI用）"""
    conn = get_db()
    row = conn.execute(
        "SELECT state, triggered_at, updated_at FROM signal_state WHERE signal_key = ?",
        (signal_key,),
    ).fetchone()
    conn.close()
    if row is None:
        return {"state": "inactive", "triggered_at": None, "updated_at": None}
    return {"state": row[0], "triggered_at": row[1], "updated_at": row[2]}


def get_all_states() -> list:
    """全 signal_key の状態（デバッグ・管理画面用）"""
    conn = get_db()
    rows = conn.execute(
        "SELECT signal_key, state, triggered_at, updated_at FROM signal_state ORDER BY signal_key"
    ).fetchall()
    conn.close()
    return [
        {
            "signal_key": r[0],
            "state": r[1],
            "triggered_at": r[2],
            "updated_at": r[3],
        }
        for r in rows
    ]


def reset_signal_state(signal_key: str) -> None:
    """指定シグナルを削除（リセット用）"""
    conn = get_db()
    conn.execute("DELETE FROM signal_state WHERE signal_key = ?", (signal_key,))
    conn.commit()
    conn.close()


def reset_all_states() -> int:
    """全状態を削除。返り値は削除件数"""
    conn = get_db()
    cur = conn.execute("DELETE FROM signal_state")
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count
