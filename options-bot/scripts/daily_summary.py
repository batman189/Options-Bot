"""Daily summary of V2 signal logs for review sessions.

Usage:
    python scripts/daily_summary.py              # today
    python scripts/daily_summary.py --date 2026-04-02
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH


def run(target_date: str):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ── V2 signal logs for the day ──
    rows = conn.execute(
        "SELECT * FROM v2_signal_logs WHERE timestamp LIKE ? ORDER BY timestamp",
        (f"{target_date}%",),
    ).fetchall()

    total = len(rows)
    entered = [r for r in rows if r["entered"]]
    rejected = [r for r in rows if not r["entered"]]

    # ── Breakdown by profile ──
    profile_stats: dict[str, dict] = {}
    for r in rows:
        name = r["profile_name"] or "unknown"
        if name not in profile_stats:
            profile_stats[name] = {"total": 0, "entered": 0, "rejected": 0}
        profile_stats[name]["total"] += 1
        if r["entered"]:
            profile_stats[name]["entered"] += 1
        else:
            profile_stats[name]["rejected"] += 1

    # ── Breakdown by regime ──
    regime_counts = Counter(r["regime"] or "unknown" for r in rows)

    # ── Top block reasons ──
    block_reasons = Counter(
        r["block_reason"] for r in rejected if r["block_reason"]
    )
    top_reasons = block_reasons.most_common(5)

    # ── Confidence stats ──
    confs = [r["confidence_score"] for r in rows if r["confidence_score"] is not None]
    avg_conf = sum(confs) / len(confs) if confs else 0.0

    # ── Learning state ──
    learning_rows = conn.execute("SELECT * FROM learning_state").fetchall()

    # ── Trades entered today ──
    trades = conn.execute(
        "SELECT * FROM trades WHERE entry_date LIKE ? ORDER BY entry_date",
        (f"{target_date}%",),
    ).fetchall()

    conn.close()

    # ── Print summary ──
    print(f"{'='*60}")
    print(f"  V2 DAILY SUMMARY - {target_date}")
    print(f"{'='*60}")
    print()

    print(f"Total evaluations:  {total}")
    print(f"Entered:            {len(entered)}")
    print(f"Rejected:           {len(rejected)}")
    print(f"Entry rate:         {len(entered)/total*100:.1f}%" if total > 0 else "Entry rate:         n/a")
    print(f"Avg confidence:     {avg_conf*100:.1f}%")
    print()

    print("-- By Profile --")
    for name in sorted(profile_stats):
        s = profile_stats[name]
        print(f"  {name:20s}  {s['total']:4d} eval  {s['entered']:3d} entered  {s['rejected']:3d} rejected")
    print()

    print("-- By Regime --")
    for regime, count in regime_counts.most_common():
        print(f"  {regime:20s}  {count:4d}")
    print()

    print("-- Top Block Reasons --")
    if top_reasons:
        for reason, count in top_reasons:
            print(f"  {count:4d}x  {reason}")
    else:
        print("  (none)")
    print()

    print("-- Trades Entered --")
    if entered:
        for r in entered:
            conf = f"{r['confidence_score']*100:.0f}%" if r['confidence_score'] else "n/a"
            print(f"  {r['timestamp'][:19]}  {r['symbol']:5s}  "
                  f"setup={r['setup_type'] or '?':16s}  conf={conf}")
    else:
        print("  (no entries)")
    print()

    if trades:
        print("-- Trade Records --")
        for t in trades:
            pnl = f"${t['pnl_dollars']:.2f}" if t["pnl_dollars"] is not None else "open"
            print(f"  {t['symbol']:5s}  {t['direction']:7s}  "
                  f"strike=${t['strike']:.0f}  qty={t['quantity']}  "
                  f"status={t['status']}  P&L={pnl}")
        print()

    print("-- Learning State --")
    if learning_rows:
        for lr in learning_rows:
            name = lr["profile_name"]
            conf = lr["min_confidence"]
            paused = bool(lr["paused_by_learning"])
            status = "PAUSED" if paused else "active"
            print(f"  {name:20s}  threshold={conf*100:.0f}%  {status}")
    else:
        print("  (no learning state in DB)")
    print()
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V2 Daily Summary")
    parser.add_argument("--date", type=str, default=date.today().isoformat(),
                        help="Date to summarize (YYYY-MM-DD, default: today)")
    args = parser.parse_args()
    run(args.date)
