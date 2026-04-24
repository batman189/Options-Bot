"""Daily summary of V2 signal logs for review sessions.

Usage:
    python scripts/daily_summary.py              # today
    python scripts/daily_summary.py --date 2026-04-02
"""

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH


def generate_summary(target_date: str, db_path: str | None = None) -> str:
    """Generate daily summary text. Returns a string (no printing).

    Shadow Mode: filters rows by the current EXECUTION_MODE. To see
    the other mode's activity, set the env var and re-run. Mixing
    modes in one report would misreport "what the bot did" since
    shadow fills never reach the broker.
    """
    from config import EXECUTION_MODE
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM v2_signal_logs "
        "WHERE timestamp LIKE ? AND execution_mode = ? "
        "ORDER BY timestamp",
        (f"{target_date}%", EXECUTION_MODE),
    ).fetchall()

    total = len(rows)
    entered_rows = [r for r in rows if r["entered"]]
    rejected_rows = [r for r in rows if not r["entered"]]

    # Breakdown by profile
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

    # Breakdown by regime
    regime_counts = Counter(r["regime"] or "unknown" for r in rows)

    # Top block reasons
    block_reasons = Counter(
        r["block_reason"] for r in rejected_rows if r["block_reason"]
    )
    top_reasons = block_reasons.most_common(5)

    # Confidence stats
    confs = [r["confidence_score"] for r in rows if r["confidence_score"] is not None]
    avg_conf = sum(confs) / len(confs) if confs else 0.0

    # Learning state
    learning_rows = conn.execute("SELECT * FROM learning_state").fetchall()

    conn.close()

    # Build output
    lines: list[str] = []
    w = lines.append

    w(f"=== OPTIONS BOT DAILY SUMMARY -- {target_date} ===")
    w("")
    w(f"SIGNAL EVALUATIONS: {total} total")

    # Find max profile name length for alignment
    names = sorted(profile_stats.keys())
    max_len = max((len(n) for n in names), default=10)
    for name in names:
        s = profile_stats[name]
        pad = " " * (max_len - len(name))
        w(f"  {name}:{pad} {s['total']} evaluated, "
          f"{s['entered']} entered, {s['rejected']} rejected")

    w("")
    w("REGIME BREAKDOWN:")
    for regime, count in regime_counts.most_common():
        w(f"  {regime}: {count} evaluations")

    w("")
    w("TOP REJECTION REASONS:")
    if top_reasons:
        for i, (reason, count) in enumerate(top_reasons, 1):
            w(f"  {i}. {reason} ({count}x)")
    else:
        w("  (none)")

    w("")
    w(f"TRADES ENTERED: {len(entered_rows)}")
    if entered_rows:
        for r in entered_rows:
            conf = f"conf={r['confidence_score']:.2f}" if r['confidence_score'] else "conf=n/a"
            # Format time as HH:MM AM/PM
            try:
                ts = r["timestamp"]
                has_tz = ts.endswith("Z") or "+" in ts[19:]
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00") if has_tz else ts)
                time_str = f"entered {dt.strftime('%-I:%M %p')}"
            except Exception:
                time_str = f"entered {r['timestamp'][:19]}"
            w(f"  {r['profile_name']} | {r['symbol']} | {conf} | {time_str}")
    else:
        w("  (none)")

    w("")
    w(f"AVERAGE CONFIDENCE: {avg_conf:.3f}")

    w("")
    w("LEARNING STATE:")
    if learning_rows:
        for lr in learning_rows:
            name = lr["profile_name"]
            conf = lr["min_confidence"]
            paused = bool(lr["paused_by_learning"])
            status = "PAUSED" if paused else "ACTIVE"
            pad = " " * (max(15 - len(name), 1))
            w(f"  {name}:{pad}{conf*100:.0f}% threshold | {status}")
    else:
        w("  (no learning state)")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V2 Daily Summary")
    parser.add_argument("--date", type=str, default=date.today().isoformat(),
                        help="Date to summarize (YYYY-MM-DD, default: today)")
    args = parser.parse_args()
    print(generate_summary(args.date))
