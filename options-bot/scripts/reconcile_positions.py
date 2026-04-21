"""Reconcile DB open trades against Alpaca positions.

Finds mismatches between what the DB thinks is open and what Alpaca
actually holds. Corrects the DB using Alpaca as source of truth.

Usage:
    python scripts/reconcile_positions.py           # dry run (show only)
    python scripts/reconcile_positions.py --fix     # apply corrections
"""

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH, ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER


def parse_occ_symbol(symbol: str) -> dict:
    """Parse OCC symbol like SPY260407P00659000."""
    m = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', symbol)
    if not m:
        return {}
    return {
        "underlying": m.group(1),
        "expiration": f"20{m.group(2)[:2]}-{m.group(2)[2:4]}-{m.group(2)[4:6]}",
        "right": "PUT" if m.group(3) == "P" else "CALL",
        "strike": int(m.group(4)) / 1000.0,
    }


def run(fix: bool = False):
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)

    # 1. Get Alpaca positions
    alpaca_positions = client.get_all_positions()
    alpaca_set = {}
    for p in alpaca_positions:
        parsed = parse_occ_symbol(p.symbol)
        if parsed:
            key = (parsed["underlying"], parsed["strike"], parsed["expiration"])
            alpaca_set[key] = {
                "qty": int(p.qty),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "current_price": float(p.current_price),
                "symbol": p.symbol,
            }

    # 2. Get DB open trades
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    db_open = conn.execute(
        "SELECT id, symbol, direction, strike, expiration, quantity, entry_price, "
        "setup_type FROM trades WHERE status = 'open'"
    ).fetchall()

    db_set = {}
    for row in db_open:
        key = (row["symbol"], row["strike"], row["expiration"])
        if key not in db_set:
            db_set[key] = []
        db_set[key].append(dict(row))

    print(f"Alpaca open positions: {len(alpaca_positions)}")
    print(f"DB open trades: {len(db_open)}")
    print()

    # 3. Find mismatches
    issues = []

    # DB says open but Alpaca doesn't have it
    for key, trades in db_set.items():
        if key not in alpaca_set:
            for t in trades:
                issues.append({
                    "type": "DB_OPEN_ALPACA_GONE",
                    "trade_id": t["id"],
                    "symbol": t["symbol"],
                    "strike": t["strike"],
                    "expiration": t["expiration"],
                    "entry_price": t["entry_price"],
                    "quantity": t["quantity"],
                    "setup_type": t.get("setup_type"),
                })

    # Alpaca has it but DB doesn't
    for key, alpaca_pos in alpaca_set.items():
        if key not in db_set:
            issues.append({
                "type": "ALPACA_OPEN_DB_MISSING",
                "symbol": key[0],
                "strike": key[1],
                "expiration": key[2],
                "alpaca_qty": alpaca_pos["qty"],
                "alpaca_value": alpaca_pos["market_value"],
            })

    if not issues:
        print("NO MISMATCHES — DB and Alpaca are in sync.")
        conn.close()
        return

    print(f"FOUND {len(issues)} MISMATCHES:")
    print()

    # 4. For DB_OPEN_ALPACA_GONE: check Alpaca order history for sells.
    # Bounded by a date window (midnight ET today) so we don't scan the
    # account's entire history; limit=500 gives headroom on busy days —
    # the old 200-order cap silently dropped sells and caused legitimate
    # exits to be booked as expired_worthless at -100%. We log a WARNING
    # if we hit the ceiling so a future operator knows to add pagination.
    alpaca_sells = {}
    _RECONCILE_ORDER_LIMIT = 500
    try:
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")
        _today_et = datetime.now(_ET).replace(hour=0, minute=0, second=0, microsecond=0)
        req = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            after=_today_et,
            limit=_RECONCILE_ORDER_LIMIT,
        )
        orders = client.get_orders(filter=req)
        if len(orders) >= _RECONCILE_ORDER_LIMIT:
            print(f"  WARNING: order fetch hit the {_RECONCILE_ORDER_LIMIT}-row ceiling. "
                  f"Some sells may be missing — pagination needed.")
        for o in orders:
            if "SELL" not in str(o.side).upper():
                continue
            if str(o.status) != "OrderStatus.FILLED":
                continue
            parsed = parse_occ_symbol(o.symbol or "")
            if not parsed:
                continue
            okey = (parsed["underlying"], parsed["strike"], parsed["expiration"])
            if okey not in alpaca_sells:
                alpaca_sells[okey] = []
            alpaca_sells[okey].append({
                "price": float(o.filled_avg_price) if o.filled_avg_price else None,
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
                "qty": int(o.qty) if o.qty else 0,
            })
    except Exception as e:
        print(f"  WARNING: could not fetch Alpaca orders: {e}")

    now_utc = datetime.now(timezone.utc).isoformat()
    # Track setup_types closed in this run so we can fire the 20-trade
    # learning trigger once per distinct setup after commit. Previously
    # reconcile-driven exits were invisible to the learner.
    closed_setup_types: set[str] = set()

    for issue in issues:
        if issue["type"] == "DB_OPEN_ALPACA_GONE":
            key = (issue["symbol"], issue["strike"], issue["expiration"])
            sells = alpaca_sells.get(key, [])
            if sells:
                fill = sells.pop(0)
                exit_price = fill["price"] or 0.0
                pnl_dollars = (exit_price - issue["entry_price"]) * issue["quantity"] * 100
                pnl_pct = ((exit_price - issue["entry_price"]) / issue["entry_price"] * 100) if issue["entry_price"] else 0
                print(f"  {issue['trade_id'][:8]} {issue['symbol']} ${issue['strike']} "
                      f"exp={issue['expiration']}: DB=open, Alpaca=SOLD @ ${exit_price:.2f} "
                      f"pnl=${pnl_dollars:.2f}")
                if fix:
                    conn.execute(
                        """UPDATE trades SET status='closed', exit_reason='alpaca_reconcile',
                           exit_price=?, pnl_dollars=?, pnl_pct=?,
                           exit_date=?, updated_at=? WHERE id=?""",
                        (exit_price, round(pnl_dollars, 2), round(pnl_pct, 2),
                         fill["filled_at"] or now_utc, now_utc, issue["trade_id"]),
                    )
                    if issue.get("setup_type"):
                        closed_setup_types.add(issue["setup_type"])
            else:
                pnl_dollars = -(issue["entry_price"] * issue["quantity"] * 100)
                print(f"  {issue['trade_id'][:8]} {issue['symbol']} ${issue['strike']} "
                      f"exp={issue['expiration']}: DB=open, Alpaca=GONE (no sell found) "
                      f"-> expired_worthless pnl=${pnl_dollars:.2f}")
                if fix:
                    conn.execute(
                        """UPDATE trades SET status='closed', exit_reason='expired_worthless',
                           exit_price=0, pnl_dollars=?, pnl_pct=-100.0,
                           exit_date=?, updated_at=? WHERE id=?""",
                        (round(pnl_dollars, 2), now_utc, now_utc, issue["trade_id"]),
                    )
                    if issue.get("setup_type"):
                        closed_setup_types.add(issue["setup_type"])

        elif issue["type"] == "ALPACA_OPEN_DB_MISSING":
            print(f"  MISSING: Alpaca has {issue['symbol']} ${issue['strike']} "
                  f"exp={issue['expiration']} x{issue['alpaca_qty']} "
                  f"value=${issue['alpaca_value']:.2f} but DB has no open trade")
            # Don't auto-insert — we don't know the entry price or profile

    if fix:
        conn.commit()
        print(f"\n{len(issues)} corrections applied to DB.")
    else:
        print("\nDRY RUN — run with --fix to apply corrections.")

    conn.close()

    # Fire the 20-trade learning trigger once per setup_type we just closed.
    # Mirrors TradeManager._maybe_trigger_learning but without the class
    # context. Default-confidence fallback chain: latest learning_state if
    # present, else 0.60.
    if fix and closed_setup_types:
        try:
            from learning.storage import (
                get_closed_trade_count, load_learning_state,
            )
            from learning.learner import run_learning
            for setup_type in closed_setup_types:
                try:
                    count = get_closed_trade_count(setup_type)
                    if count > 0 and count % 20 == 0:
                        prior = load_learning_state(setup_type)
                        default_conf = prior.min_confidence if prior else 0.60
                        print(f"  Learning trigger ({count} closed) for {setup_type}")
                        run_learning(setup_type, default_conf)
                except Exception as e:
                    print(f"  WARN: learning trigger for {setup_type} failed: {e}")
        except Exception as e:
            print(f"  WARN: could not import learning module: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile DB vs Alpaca positions")
    parser.add_argument("--fix", action="store_true", help="Apply corrections (default: dry run)")
    args = parser.parse_args()
    run(fix=args.fix)
