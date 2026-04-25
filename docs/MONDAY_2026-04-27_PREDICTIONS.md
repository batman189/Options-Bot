# Monday 2026-04-27 — Shadow-Mode Trading Predictions

Filed: 2026-04-25 (Saturday). First full session of shadow mode.
Anchor: Thursday 2026-04-23 ran 778 signal evaluations and 0 entries
(PDT-locked the entire post-9:30am window). Friday 2026-04-24 was lost
to context overrun; no data. Monday is the first session where shadow
mode replaces the PDT block and lets signals reach Step 8.

This document is a calibration exercise. Concrete numbers go on the
record before market open so reality can refute them. Anything that
ships dramatically wrong on Monday is a lesson, not a comment.

---

## 1. Volume predictions

| Metric | Prediction | Reasoning |
| --- | --- | --- |
| Total signal evaluations (full day) | 700-900 | Thursday was 778 with normal regime activity. Monday should land in the same envelope unless one symbol gets unusually quiet (compresses scanner activity) or a macro event fires multiple veto windows. |
| Entries that fire (pass all gates) | **3-8** | Thursday had 0 only because PDT blocked everything at Step 7. ~76 signals reached PDT lock — most were re-evaluations of the same setup across iterations. With 10-30 min cooldowns per profile, the practical entry ceiling is around 8-12. Realistic floor: 3 (regime/confidence still kills most). |
| scalp_0dte share | 2-4 | scalp_0dte sees the most setups in the data because it accepts 4 setup_types (momentum/mean_reversion/compression_breakout/macro_trend). Lower confidence threshold (0.55 vs 0.65) helps too. |
| momentum share | 0-2 | Higher threshold (0.65). Thursday saw 172 evaluations and the modal rejection was "regime CHOPPY not supported." If Monday opens TRENDING the count could go higher. |
| mean_reversion share | 0-2 | 14:00 ET cutoff caps the window. Setup needs RSI extremes which we did not see Thursday. |
| catalyst share | **0** likely | Sentiment threshold 0.7 is rarely met by the FinBERT cache. Thursday: 55 catalyst-specific rejections, 0 entries. |
| swing / tsla_swing share | 0-1 | Only 11 evaluations each Thursday. Low signal volume is normal. |
| Entries by 11:00 AM ET | 1-3 | First 90 minutes is when scalp_0dte and momentum see real moves. If 0 by 11:00 AM and the regime is TRENDING, something's wrong with the entry path. |

**Honest framing:** the 3-8 number is itself a guess. The most-blocked path
on Thursday was confidence-below-threshold, not PDT. Removing PDT does not
make low-confidence signals enter; it only unblocks the ones that already
passed scoring. So the *real* question is what the confidence distribution
looks like on Monday — addressed in §3.

---

## 2. Kill-funnel predictions

Top rejection reasons, ranked. Thursday's order is the prior:

| # | Predicted | Thursday actual | Why this rank |
| --- | --- | --- | --- |
| 1 | regime not supported by `<profile>` | 78x same | Regime mismatch is profile-structural, not market-state-dependent. CHOPPY days kill 30-50% of momentum/swing signals at the door. |
| 2 | `confidence < 0.600` (or 0.650) | 60+ across many sub-buckets | This is the dominant filter once regime passes. Thursday had ~200 confidence rejections across all bucketed values; combined they outweigh any single string. |
| 3 | `no_entry_after_et_hour: 14:xx >= 14:00` | 62x | Hard fact about mean_reversion + later-day signals. Will appear from 18:00 UTC onward. |
| 4 | profile-specific checks (catalyst sentiment / mean_reversion RSI / momentum directional bars) | 50-150x combined | Each profile's `_profile_specific_entry_check` blocks signals the scorer would otherwise let through. |
| 5 | `no_qualifying_contract` | low single digits | Strikes the post-Step-6 path; only fires when the chain has nothing in the moneyness/spread/OI window. |

**Where rejections will NOT appear:**
- `pdt_locked` — **predicted 0 rows.** Shadow mode bypasses PDT entirely. If
  this appears, something is wrong with the divert.
- `pdt_rejected_at_submit` — also **0**. No Alpaca submit happens.
- `pdt_day_trades_exhausted` — also **0**. Same reason.

**New rejection reasons that may appear:**
- `shadow_quote_unavailable` — fires if ThetaData returns None/0/exception
  at the moment of synthetic fill. Probably **0-3x** for a clean session,
  but spikes if ThetaData has any hiccup.
- `submit_exception: <type>` — should be **0** in shadow mode (no Alpaca
  call). If it appears, the divert leaked.

---

## 3. Confidence distribution

| Metric | Prediction | Thursday |
| --- | --- | --- |
| Mean confidence across all evaluations | 0.45-0.55 | 0.498 |
| % above 0.60 (entry threshold for momentum/general) | 12-18% | ~13% |
| % above 0.75 (high-conviction tier) | 2-5% | unknown without re-querying |
| % above scalp_0dte's 0.55 | 18-25% | unknown |

The shape should be roughly right-skewed with a long left tail of
rejected-by-confidence rows. If the mean shifts above 0.55 that's
a sign the seed data or scorer changed; investigate.

---

## 4. P&L predictions

This is the section I'm least confident about. Real numbers:

| Question | Prediction |
| --- | --- |
| Direction | I genuinely do not know. ~55/45 leaning negative because shadow fills are mid-to-mid (no slippage), and even small adverse selection through the day can put 3-8 trades net negative. |
| Best case | +$200 to +$500 if 4-5 trades land on the right side of the move. Concentrated SPY 0DTE delta is the only way single-day P&L gets there at this account size. |
| Expected case | -$50 to +$100 (small noise around zero). Bot's edge is unproven; first day is a coin flip. |
| Worst case | -$300 to -$500. Two losers stacked on max-position scalp_0dte trades during a CHOPPY whipsaw afternoon. |
| Win rate on N=5 | 2/5 to 3/5. The model's calibrated CV accuracy is 62.7% but live data is OOD versus training. I'd be surprised at 4/5 and very surprised at 5/5. |
| Largest single position size | $200-400. Sizer halving rules + 25% max position on $5145 equity. ~5 contracts at ~$0.75 premium = $375. |
| Largest single-trade gain | +$100 to +$250. Scalp 0DTE on a clean breakout: 30-50% premium gain on a $200 position = $60-100. A two-strike breakout move could hit $250. |
| Largest single-trade loss | -$80 to -$200. 25% stop on a $200-400 position = $50-100. -$200 if a stop slips. |

**The dollar predictions are loose.** What I'd call a real success is the
*distribution* of trades looking sane, not the dollar number landing in
any specific range.

---

## 5. Behavioral predictions

| Question | Prediction |
| --- | --- |
| First profile to fire | scalp_0dte. Lower threshold + no time cutoff + 4 accepted setup_types = highest hit rate in the first 90 minutes. |
| Profile that won't fire at all | catalyst (FinBERT cache rarely produces sentiment > 0.7). Possibly tsla_swing on a quiet TSLA day. |
| Macro veto fires | 0-1 times. The macro layer is hourly-polled; HIGH-impact events are rare and only fire a 15-minute buffer around the event itself. Monday morning has no scheduled FOMC/CPI; a Powell speech is the only realistic trigger. |
| Regime change during the day | Likely **CHOPPY → TRENDING_UP/DOWN at some point**, then maybe back. Thursday was CHOPPY 402 / TRENDING_DOWN 376 — the regime detector clearly toggles intraday. The question is whether momentum profile catches the trending window or arrives after the move. |
| Most common exit type | **trailing_stop** if any winners. **stop_loss** if any losers. **time-based / EOD force-close** for any 0DTE that didn't hit a target by 15:45 ET. `thesis_broken` is unlikely unless ThetaData has a brief outage that makes scalp_0dte's `_evaluate_thesis` return None (Bot Problems #12). |

---

## 6. What I'm NOT confident about

In rough order of how much it bothers me:

1. **I do not know how the scorer behaves under a fresh-cold scorer
   trade history.** Shadow mode filters `historical_perf` to
   `execution_mode='shadow'`, which has zero rows on day one. So
   `historical_perf` will return the 0.5 neutral prior for every
   symbol/setup_type combination. That's a 17.6% factor weight pinned
   at neutral; the score is effectively a 5-factor model on day one
   instead of 6. Whether that's a small effect or a big one — I don't
   know.

2. **I don't know if the implied-move-gate-bypassed-for-classifiers
   fix is over-permissive in regimes I haven't watched it run in.**
   Per the memory, the bypass exists because confidence × avg_move can
   never beat straddle cost. Fine in TRENDING regimes. In CHOPPY
   regimes the avg_move-only EV gate may let through trades that a
   directional confidence check would have blocked.

3. **I don't know if `min_confidence=0.55` for scalp_0dte is too
   permissive at scale.** Thursday's scalp_0dte saw confidence values
   around 0.35-0.45, all rejected. If Monday produces values just
   above 0.55, those will trade — but the OOD calibration of the
   isotonic regressor on real-day data is untested.

4. **I don't know whether ThetaData latency at open will produce
   `shadow_quote_unavailable` rejections.** The simulator refuses to
   fake fills; if ThetaData has the typical 9:30:00-9:30:30 ET startup
   warmup, signals firing in that window may all reject.

5. **I don't know if the cooldown timer (`_last_entry_time` per
   profile) is being honored cleanly across profile re-entries
   under shadow mode.** Tests cover the live path. Shadow set
   `_last_entry_time` BEFORE the synchronous dispatch (different from
   live); if there's an interaction with the trade_manager state
   I didn't anticipate, multi-entry could happen.

6. **I don't know what the actual underlying liquidity will be at
   open.** Bid-ask spreads on SPY 0DTE at 9:31 ET can be $0.05-$0.20
   wide; the simulator pays the mid, so a 5% spread becomes a free
   2.5% per direction. Shadow P&L will look better than live would.

---

## 7. What would shock me

If any of these happen Monday, I will treat it as a bug indicator and
investigate **before reading any P&L number**.

| Event | Why it would be alarming |
| --- | --- |
| Zero trades all day | The PDT removal should produce *something*. If 0, the divert is broken or every signal is being killed by a filter I'm not tracking. |
| 30+ trades | Either cooldowns are broken or the scorer is producing wildly inflated confidence values. The ceiling at $5k account size with 10-min scalp cooldowns is closer to 25 across all profiles. |
| catalyst fires more than 1 time | The sentiment > 0.7 gate hasn't fired in any production data I've seen. If catalyst trades, FinBERT got a crisp positive signal that's worth investigating. |
| `pdt_locked` rows in v2_signal_logs | The shadow divert is broken. Step 7 should never reach the PDT branch under EXECUTION_MODE=shadow. |
| `submit_exception` rows of any kind | The divert leaked through to Alpaca. Investigate immediately; that's the worst-case bug for shadow mode. |
| All trades fire in a single 15-minute window | Cooldown timer is broken or the signal stream has a stuck-state bug. |
| Bot enters a position with `execution_mode='live'` in the trades table | The divert tagged the wrong mode. Critical bug. |
| The amber UI banner is missing | Backend is reporting `live` to `/api/execution/mode`. EXECUTION_MODE env var didn't propagate or `start_backend` log lied. |
| `historical_perf` for any non-zero contribution to a score | Shadow has 0 closed trades; the factor MUST be 0.5 neutral all day. Anything else means the mode filter leaked. |
| `thesis_broken` exits clustering on the same minute | ThetaData outage. Bot Problems #12 — log it for the next learning cycle. |

---

## 8. Success criteria

Before reading any P&L number Monday evening, the day succeeds at
these levels:

**Minimum bar (the day produced any value):**
- Backend stayed up the full session with no crashes.
- Amber banner visible all day.
- At least 1 entry fired through the simulator.
- Trade row in DB tagged `execution_mode='shadow'` with sane fill price.
- No `submit_exception` or `pdt_locked` rows (proves the divert held).

**Good day (quietly satisfied):**
- Minimum bar achieved.
- 3-8 entries spread across at least 2 profiles.
- Kill funnel matches §2 predictions within a factor of 2.
- At least one profile (probably scalp_0dte) traded as designed —
  entered on a real setup, exited on profit_target / trailing_stop /
  stop_loss, not stuck in a bad state.
- No item from §7 (shock list) triggered.

**Great day (genuinely excited):**
- All "good day" conditions plus:
- Confidence distribution lines up with §3 predictions.
- At least one trade win, at least one trade loss (proves the model
  is producing a real distribution, not all-up or all-down noise).
- Shadow P&L within ±$200 of zero (the *direction* is noise; the
  *magnitude* being small means slippage assumptions roughly match).
- Operator (you) finishes the day understanding *why* each trade
  fired, not just that it did.

**P&L is explicitly NOT a success criterion.** First-day shadow data
is too noisy to read as signal-quality evidence. The first signal
worth reading is whether the kill funnel and entry distribution match
expectations. Net dollars come later, after a week of data.

---

## 9. Re-read this Monday at EOD

After the close, before reading the daily summary:
1. Re-read §6 (what I wasn't confident about). Did Monday answer any of those?
2. Re-read §7 (shock list). Did anything fire? Investigate before P&L.
3. Then look at the funnel. Compare to §2.
4. Then the entries. Compare to §1.
5. Confidence distribution last. Compare to §3.
6. P&L absolutely last. It's the noisiest signal of the bunch.

If §1-§3 all match within a factor of 2 and no §7 item fired,
Monday was a successful first session regardless of P&L sign.

---

*Filed by: agent (Claude Opus 4.7) on 2026-04-25.
Operator (Andrew) signs off on the predictions before market open.*
