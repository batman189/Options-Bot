"""Backfill trades table from Alpaca order history.

Reads all filled orders from Alpaca for a given date, inserts BUY orders
as new trade rows, and matches SELL orders to update exit fields.

Usage:
    python scripts/backfill_today_trades.py                  # today
    python scripts/backfill_today_trades.py --date 2026-04-06
"""

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH, ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER


def parse_option_symbol(symbol: str) -> dict:
    """Parse OCC option symbol like SPY260407P00659000.
    Returns dict with underlying, expiration, right, strike."""
    m = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', symbol)
    if not m:
        return {}
    underlying = m.group(1)
    exp_raw = m.group(2)
    right = "PUT" if m.group(3) == "P" else "CALL"
    strike = int(m.group(4)) / 1000.0
    expiration = f"20{exp_raw[:2]}-{exp_raw[2:4]}-{exp_raw[4:6]}"
    return {
        "underlying": underlying,
        "expiration": expiration,
        "right": right,
        "strike": strike,
    }


def run(target_date: str):
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)

    dt = datetime.strptime(target_date, "%Y-%m-%d")
    req = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        after=dt,
        limit=500,
    )
    orders = client.get_orders(filter=req)
    filled = [o for o in orders if str(o.status) == "OrderStatus.FILLED"]
    print(f"Alpaca filled orders on/after {target_date}: {len(filled)}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    inserted = 0
    updated = 0
    skipped = 0

    # Sort by filled_at so buys come before sells
    filled.sort(key=lambda o: o.filled_at or datetime.min.replace(tzinfo=timezone.utc))

    for order in filled:
        symbol = order.symbol
        parsed = parse_option_symbol(symbol)
        if not parsed:
            print(f"  SKIP: cannot parse symbol {symbol}")
            skipped += 1
            continue

        alpaca_id = str(order.id)
        side = str(order.side)
        filled_at = order.filled_at.isoformat() if order.filled_at else None
        filled_price = float(order.filled_avg_price) if order.filled_avg_price else None
        qty = int(order.qty) if order.qty else 0

        if "BUY" in side.upper():
            # Check if already exists by alpaca order ID stored in id field
            existing = conn.execute(
                "SELECT id FROM trades WHERE id = ?", (alpaca_id,)
            ).fetchone()
            if existing:
                print(f"  SKIP BUY: {alpaca_id[:8]} already in trades")
                skipped += 1
                continue

            # Also check for duplicate by symbol+strike+entry_date (within 2 seconds)
            dup = conn.execute(
                """SELECT id FROM trades WHERE symbol = ? AND strike = ?
                   AND expiration = ? AND entry_date = ?""",
                (parsed["underlying"], parsed["strike"],
                 parsed["expiration"], filled_at),
            ).fetchone()
            if dup:
                print(f"  SKIP BUY: duplicate {symbol} strike={parsed['strike']} at {filled_at}")
                skipped += 1
                continue

            now_utc = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO trades (
                       id, profile_id, profile_name, symbol, direction, strike, expiration,
                       quantity, entry_price, entry_date, setup_type,
                       confidence_score, market_regime,
                       status, created_at, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    alpaca_id,
                    "backfill",  # No profile_id available from Alpaca
                    "backfill",  # Prompt 16: sentinel matches profile_id convention
                    parsed["underlying"],
                    parsed["right"],
                    parsed["strike"],
                    parsed["expiration"],
                    qty,
                    filled_price,
                    filled_at,
                    "catalyst",  # All today's entries were catalyst
                    None,  # No confidence from Alpaca data
                    None,  # No regime from Alpaca data
                    "open",
                    now_utc,
                    now_utc,
                ),
            )
            conn.commit()
            inserted += 1
            print(f"  INSERT: {alpaca_id[:8]} BUY {symbol} x{qty} @ ${filled_price:.2f} at {filled_at}")

        elif "SELL" in side.upper():
            # Find the matching open trade: same underlying, strike, expiration
            match = conn.execute(
                """SELECT id, entry_price FROM trades
                   WHERE symbol = ? AND strike = ? AND expiration = ?
                   AND status = 'open'
                   ORDER BY entry_date ASC LIMIT 1""",
                (parsed["underlying"], parsed["strike"], parsed["expiration"]),
            ).fetchone()

            if not match:
                print(f"  SKIP SELL: no matching open trade for {symbol}")
                skipped += 1
                continue

            entry_price = match["entry_price"]
            pnl_dollars = (filled_price - entry_price) * qty * 100 if entry_price else None
            pnl_pct = ((filled_price - entry_price) / entry_price * 100) if entry_price else None

            now_utc = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """UPDATE trades SET
                       exit_price = ?, exit_date = ?, exit_reason = ?,
                       pnl_dollars = ?, pnl_pct = ?, status = 'closed',
                       updated_at = ?
                   WHERE id = ?""",
                (
                    filled_price, filled_at, "eod_close",
                    round(pnl_dollars, 2) if pnl_dollars is not None else None,
                    round(pnl_pct, 2) if pnl_pct is not None else None,
                    now_utc,
                    match["id"],
                ),
            )
            conn.commit()
            updated += 1
            entry_str = f"${entry_price:.2f}" if entry_price else "?"
            pnl_str = f"${pnl_dollars:.2f}" if pnl_dollars is not None else "?"
            print(f"  UPDATE: {match['id'][:8]} SELL {symbol} x{qty} @ ${filled_price:.2f} "
                  f"(entry={entry_str} pnl={pnl_str})")

    conn.close()

    print(f"\n=== Summary ===")
    print(f"  Inserted: {inserted}")
    print(f"  Updated:  {updated}")
    print(f"  Skipped:  {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill trades from Alpaca")
    parser.add_argument("--date", type=str,
                        default=datetime.now().strftime("%Y-%m-%d"),
                        help="Date to backfill (YYYY-MM-DD)")
    args = parser.parse_args()
    run(args.date)
