# Shadow Execution Mode

This document is the operator reference for shadow mode. For the conceptual overview,
see the **Shadow Execution Mode** section in `ABOUT.md`.

## Starting shadow mode

1. `cd options-bot/ui && npm run build` — rebuilds the UI dist with the latest banner
   markup. Required after every clone or after any `ui/src/**` edit, since `ui/dist/assets/`
   is `.gitignore`d.
2. Set `EXECUTION_MODE=shadow` in the environment. Either export it in the shell or add
   it to `.env` next to `ALPACA_API_KEY` / `THETADATA_USERNAME`.
3. Restart the backend: `python options-bot/main.py`.
4. Verify the amber banner is visible at the top of every page in the UI.
5. Verify `curl http://localhost:8000/api/execution/mode` returns `{"mode":"shadow",...}`.
6. Watch the logs for the first signal evaluation — it should log
   `EXECUTION_MODE=shadow — orders will be simulated locally, NO submissions to Alpaca.`
   at startup, and once a signal scores high enough to enter, the line should read
   `Step 8: SHADOW ORDER ...` instead of `Step 8: ORDER ...`.

> **Resolved 2026-04-25 (Prompt 35):** `main.py`'s embedded pipeline-trace
> startup-guard previously failed under `EXECUTION_MODE=shadow` because test
> 15.1 seeded trades via raw INSERT (relying on the `execution_mode`
> DB-default of `'live'`) and then read them back through the mode-filtered
> learning storage layer. The fix introduced `_execution_mode(mode)` — a
> context manager near the top of `test_pipeline_trace.py` that pins
> `config.EXECUTION_MODE` for the duration of a test block — and added an
> explicit `execution_mode='live'` kwarg to `_seed_closed_trades`. Tests
> 12.2, 12.3 (both cases), 14.2, 15.x, and 34.4–34.7 now wrap their
> assertions in `with _execution_mode("live"): try: ...`. A new test
> `15.1_shadow` exercises the same path under `_execution_mode("shadow")`
> with shadow-tagged seeds as a regression guard. Backend startup now
> succeeds in both modes.

## Writing tests that touch shadow-mode-filtered storage

After Commit C of the shadow rollout, several read paths filter by
`config.EXECUTION_MODE`:

- `scoring.scorer.load_trade_history_from_db`
- `learning.storage.load_trade_outcomes` and `get_closed_trade_count`
- `risk.risk_manager.get_open_position_count` and `check_portfolio_exposure`
- `scripts.daily_summary.generate_summary`

If your test seeds rows in `trades` or `v2_signal_logs` and reads them
back through any of those, you must pin the runtime mode to match the
seed. Use the helper at the top of `tests/test_pipeline_trace.py`:

```python
# 1. Test that runs in BOTH modes against live-tagged data — most common
with _execution_mode("live"):
    ids = _seed_closed_trades(10, "momentum", "test_X")  # default mode='live'
    # ... assertions through Scorer.load_trade_history_from_db, etc.

# 2. Shadow-specific test — verify the shadow path explicitly
with _execution_mode("shadow"):
    ids = _seed_closed_trades(10, "momentum", "test_X_shadow",
                              execution_mode="shadow")
    # ... shadow-runtime assertions

# 3. Live-specific test — same as case 1 but with intent documented
with _execution_mode("live"):
    ...
```

**Default fixture mode is `'live'`** because that is the DB column default
and the dominant historical pattern. Tests that wrote raw INSERTs without
specifying `execution_mode` always landed in the `'live'` bucket; we
preserve that behavior to avoid invalidating existing fixtures.

## Flipping back to live

1. Set `EXECUTION_MODE=live` (or unset the env var entirely — `live` is the default).
2. Restart the backend.
3. Verify the amber banner is **gone** in the UI.
4. Verify `curl http://localhost:8000/api/execution/mode` returns `{"mode":"live",...}`.
5. Confirm Alpaca account state is healthy: `daytrade_count` known and within budget,
   `daytrading_buying_power > 0` or `equity >= $25,000`, no broker-side ghost orders.
6. New trades will write `execution_mode='live'`. Shadow history is preserved on its
   own row tag — never mixed into live P&L by default. Use `?execution_mode=shadow` on
   `/api/trades`, `/api/v2signals`, etc. to inspect the shadow stream after the flip.
7. See the full flip-back checklist below for the additional safety items.

## What shadow mode does

When `EXECUTION_MODE=shadow`, calls to `self.submit_order` inside
`v2_strategy._submit_entry_order` / `_submit_exit_order` are diverted to
`execution.shadow_simulator.ShadowSimulator`. The simulator:

1. Fetches a fresh mark for the option contract via `self.get_last_price`.
2. If the quote is `None`, `<= 0`, or the fetcher raises — returns `None`. The strategy
   maps this to `block_reason="shadow_quote_unavailable"` (entries) or holds `pending_exit`
   and re-evaluates next cycle (exits). **Shadow mode never fakes a fill.**
3. Applies `SHADOW_FILL_SLIPPAGE_PCT` symmetrically (buys up, sells down).
4. Constructs a `SyntheticOrder` with the fields `on_filled_order` reads today
   (`identifier` prefixed `shadow-`, `side`, `quantity`, `filled_price`, `asset`,
   `symbol`, `status="filled"`).
5. Invokes `strategy.on_filled_order` **synchronously**. Live mode dispatches this
   asynchronously via Lumibot — downstream code must be insensitive to the ordering.

## Environment variables

| Variable | Default | Values | Meaning |
| --- | --- | --- | --- |
| `EXECUTION_MODE` | `live` | `live`, `shadow` | Process-wide execution mode. Immutable at runtime. |
| `SHADOW_FILL_SLIPPAGE_PCT` | `0` | float 0-100 | Symmetric fill slippage for the simulator. |

## DB columns

Both `trades.execution_mode` and `v2_signal_logs.execution_mode` are `TEXT NOT NULL DEFAULT 'live'`.
Migration is idempotent — re-running `init_db()` on an already-migrated DB is a no-op.

## Query filter convention

| Caller | Filter | Rationale |
| --- | --- | --- |
| `scoring.scorer.load_trade_history_from_db` | current mode | learning isolation |
| `learning.storage.load_trade_outcomes` + `get_closed_trade_count` | current mode | learning isolation |
| `risk.risk_manager.get_open_position_count` + `check_portfolio_exposure` | current mode | per-mode risk budget |
| `v2_strategy` open-count Step 5b + `_reload_open_positions` | current mode | restart + cap accounting |
| `management.trade_manager._cleanup_stale_trades` | hardcoded `live` | Alpaca reconcile only |
| `scripts.reconcile_positions.run` | hardcoded `live` | Alpaca reconcile only |
| `scripts.backfill_today_trades` | hardcoded `live` | Alpaca backfill only |
| `scripts.daily_summary.generate_summary` | current mode | operator report |
| `/api/trades*` + `/api/v2signals` UI routes | current mode, `execution_mode` query param overrides (`live`/`shadow`/`all`) | UI default follows bot, operator can compare |

## Callbacks NOT exercised under shadow

- `on_canceled_order`
- `on_error_order`

Shadow fills never cancel or error. Any bug living exclusively in those paths will only
appear on the mode switch back to live. This is an accepted limitation.

## Flip-back checklist (shadow → live)

Run this before unsetting `EXECUTION_MODE=shadow` for the first real trade:

- [ ] `EXECUTION_MODE` env var is `live` (or unset) on the host.
- [ ] Alpaca account state healthy:
  - [ ] `daytrade_count` known and fits the rolling 5-day budget
  - [ ] `daytrading_buying_power` > 0 OR `equity >= $25,000`
  - [ ] No open orders at broker that DB doesn't know about (run
        `scripts/reconcile_positions.py` dry-run; investigate before `--fix`)
- [ ] Recent shadow P&L is sensible:
  - [ ] Win rate in line with the strategy's prior live performance
  - [ ] No slippage blind spots — real-market spreads at the time of entry / exit
        would not have blown the trade beyond simulated cost
- [ ] Scorer `historical_perf` state reviewed:
  - [ ] `scoring.scorer.load_trade_history_from_db` under `EXECUTION_MODE=live`
        returns a usable volume OR the profile is prepared for a cold start
  - [ ] `learning_state` under live mode is current, not stale
- [ ] Risk budget understood:
  - [ ] `MAX_TOTAL_EXPOSURE_PCT`, `MAX_TOTAL_POSITIONS`, per-profile
        `max_concurrent_positions` all verified against the expected first trades
- [ ] All known shadow-only caveats reviewed (see section above).
- [ ] Shadow UI banner no longer rendering after restart (visual confirmation).
- [ ] First live trade run supervised — do not leave unattended the first hour.

## Known caveats

1. **Mid-price fills are optimistic.** Real fills sit closer to ask for buys, bid for
   sells. Tune `SHADOW_FILL_SLIPPAGE_PCT` based on observed spreads over a week.
2. **No partial fills, rejections, or network errors in shadow.** Only the happy path
   is exercised.
3. **`on_canceled_order` / `on_error_order` never fire under shadow.** See above.
4. **Prompt 30's Lumibot `order.identifier` mutation** is only exercised in live.
   Shadow uses `"shadow-<uuid4>"` prefix directly.
5. **Third-party DB consumers outside this repo are not audited.** Any external tool
   reading `trades` must filter by `execution_mode` or it will blend streams.

## Files touched

- `options-bot/config.py` — `EXECUTION_MODE`, `SHADOW_FILL_SLIPPAGE_PCT`
- `options-bot/execution/shadow_simulator.py` — simulator
- `options-bot/strategies/v2_strategy.py` — divert at `_submit_entry_order`,
  `_submit_exit_order`; open-count, reload, learning feed filter by mode
- `options-bot/backend/database.py` — schema + migrations + `write_v2_signal_log`
  execution_mode tag
- `options-bot/backend/routes/execution.py` — `GET /api/execution/mode`
- `options-bot/backend/routes/trades.py`, `v2signals.py` — `execution_mode` query param
- `options-bot/backend/schemas.py` — `TradeResponse.execution_mode`
- `options-bot/scoring/scorer.py`, `options-bot/learning/storage.py`,
  `options-bot/risk/risk_manager.py`, `options-bot/management/trade_manager.py` —
  per-mode query filtering
- `options-bot/scripts/reconcile_positions.py`, `backfill_today_trades.py`,
  `daily_summary.py` — live-only or mode-filtered queries
- `options-bot/ui/src/components/ExecutionModeBanner.tsx` — banner
- `options-bot/ui/src/pages/Trades.tsx` — SHADOW badge + row tint
- `options-bot/ui/src/types/api.ts` — `ExecutionModeInfo`, `Trade.execution_mode`
- `options-bot/ui/src/api/client.ts` — `api.execution.mode`
