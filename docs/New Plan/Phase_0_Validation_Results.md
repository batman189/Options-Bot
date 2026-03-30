# Phase 0: Infrastructure Validation Results

**Run date:** 2026-03-30 (market hours, pre-open)
**Run by:** Claude Code
**Purpose:** Validate every external dependency returns real, usable values before any build work begins.

---

## 0A - Alpaca Connection and Data Quality

### Test 1: Stock Bars (SPY + TSLA, 1-minute, SIP feed)

**PASS**

```
API Key: PKSY26ZM...6UU5 (paper account PA33VZMGU4WO)

=== SPY Last 5 1-Minute Bars (SIP feed) ===
  2026-03-30 09:52:00+00:00 | O=636.85 H=637.11 L=636.85 C=637.11 V=1427
  2026-03-30 09:53:00+00:00 | O=637.10 H=637.19 L=636.98 C=636.98 V=1824
  2026-03-30 09:54:00+00:00 | O=636.96 H=637.01 L=636.96 C=637.01 V=230
  2026-03-30 09:55:00+00:00 | O=636.95 H=636.95 L=636.95 C=636.95 V=111
  2026-03-30 09:56:00+00:00 | O=636.93 H=636.93 L=636.93 C=636.93 V=129

=== TSLA Last 5 1-Minute Bars (SIP feed) ===
  2026-03-30 09:52:00+00:00 | O=362.24 H=362.72 L=362.24 C=362.71 V=2542
  2026-03-30 09:53:00+00:00 | O=362.73 H=362.84 L=362.65 C=362.65 V=1177
  2026-03-30 09:54:00+00:00 | O=362.83 H=362.88 L=362.73 C=362.85 V=1327
  2026-03-30 09:55:00+00:00 | O=362.77 H=362.90 L=362.70 C=362.84 V=1755
  2026-03-30 09:56:00+00:00 | O=362.90 H=363.05 L=362.90 C=363.05 V=871
```

- All fields populated (timestamp, OHLCV)
- Feed confirmed as SIP (not IEX)
- Data is pre-market (timestamps are UTC, 09:52 UTC = 5:52 AM ET)
- Volume is lower because market hasn't opened yet

### Test 2: Options Chain (SPY, nearest expiration)

**PASS with limitations**

```
=== SPY Options Chain (exp=2026-03-30) ===
Total contracts returned: 342

SPY260330P00580000: bid=0.00 ask=0.01 vol=30   oi=?
SPY260330P00565000: bid=0.00 ask=0.01 vol=1    oi=?
SPY260330C00675000: bid=0.00 ask=0.01 vol=2    oi=?
SPY260330P00940000: bid=300.31 ask=303.08 vol=? oi=?
SPY260330P00626000: bid=0.05 ask=0.06 vol=35   oi=?
SPY260330C00505000: bid=131.92 ask=134.71 vol=? oi=?
SPY260330P00585000: bid=0.00 ask=0.01 vol=5    oi=?
SPY260330C00825000: bid=0.00 ask=0.01 vol=?    oi=?
SPY260330C00616000: bid=22.06 ask=22.37 vol=1   oi=?
SPY260330P00641000: bid=3.29 ask=3.33 vol=3     oi=?
```

- 342 contracts returned for today's expiration
- Bid/ask prices are populated
- Volume available on some contracts
- **Open Interest: NOT available** from Alpaca chain API
- Chain is functional but incomplete for risk analysis

### Test 3: Greeks from Alpaca

**FAIL - Greeks NOT available from Alpaca**

```
Greeks: NOT AVAILABLE from Alpaca (on all 10 contracts tested)
```

The `OptionSnapshot` object from Alpaca's chain API does not include a `greeks` attribute. Delta, gamma, theta, vega, and IV are all absent. This is consistent with Alpaca's documentation — they provide quotes and trades but not computed Greeks.

**Impact:** The bot MUST compute Greeks independently. Current approach uses Lumibot's Black-Scholes computation with a fallback delta estimator for contracts where BS fails. ThetaData would provide real Greeks but is not running.

---

## 0B - ThetaData Connection and Data Quality

**FAIL - Terminal not running**

```
ThetaData Terminal NOT RUNNING (connection refused on port 25503)
ThetaData v3 also not available
```

The Theta Data Terminal application is not currently running on the machine. When running, it serves data on port 25503 (v2) and port 25510 (v3).

**Impact:** Without ThetaData:
- No real-time Greeks (delta, gamma, theta, vega) from market data
- No historical EOD options data for training
- No implied volatility from market prices
- Bot falls back to Black-Scholes computed Greeks (less accurate but functional)

**Action required:** Start Theta Data Terminal before running any Phase 1+ validation. The bot can operate without it using fallback Greeks, but model training requires historical options data.

---

## 0C - VIX via Yahoo Finance

**PASS**

```
VIX last 10 trading days:
  2026-03-17 | Close=22.37 | High=24.58 | Low=21.87
  2026-03-18 | Close=25.09 | High=25.13 | Low=21.47
  2026-03-19 | Close=24.06 | High=27.52 | Low=23.54
  2026-03-20 | Close=26.78 | High=29.28 | Low=23.68
  2026-03-23 | Close=26.15 | High=31.04 | Low=20.28
  2026-03-24 | Close=26.95 | High=27.94 | Low=25.64
  2026-03-25 | Close=25.33 | High=26.67 | Low=24.82
  2026-03-26 | Close=27.44 | High=28.49 | Low=26.12
  2026-03-27 | Close=31.05 | High=31.65 | Low=27.54
  2026-03-30 | Close=29.70 | High=31.32 | Low=29.33

Current VIX: 29.70
```

- Historical data available (10 trading days shown)
- Current real-time value accessible
- VIX is elevated (29.70) — reflecting recent market selloff
- Data updates during market hours confirmed by the 2026-03-30 entry

**Note:** The current bot uses VIXY (a VIX ETF proxy) via Lumibot's `get_last_price()`. Yahoo Finance provides the actual ^VIX index directly and should be preferred for accuracy. The V2 build should switch to Yahoo Finance as the primary VIX source.

---

## 0D - FinBERT Sentiment

**FAIL - Library not installed**

```
transformers library not installed.
Run: pip install transformers torch
```

The `transformers` and `torch` libraries are not currently installed in the Python environment. These are required for running ProsusAI/finbert locally.

**Action required:**
1. `pip install transformers torch` (this will download ~2GB of model weights on first run)
2. Re-run the validation test with the three sample headlines
3. Confirm inference runs in under 2 seconds per headline

**Current state:** The existing bot uses TextBlob for sentiment (in `features/sentiment.py`) which is much simpler and less accurate than FinBERT. The V2 architecture calls for replacing TextBlob with FinBERT.

---

## 0E - Alpaca Order Execution (Paper)

**PASS**

```
Account: PA33VZMGU4WO
Equity: $5,000.00
Buying Power: $10,000.00
Status: ACTIVE
PDT flag: False

Open positions: 0
Pending orders: 0
```

- Paper account is active and properly funded ($5,000)
- Buying power is $10,000 (2x margin)
- No open positions or pending orders (clean slate)
- PDT flag is False (expected for new account under $25K)

**Order lifecycle verified from prior session:** Trade 505466a5 (SPY PUT $634 0DTE) was successfully placed on 2026-03-27 via `create_order()` + `submit_order()`, confirming the full order placement pipeline works through Lumibot/Alpaca.

---

## Summary Table

| Checkpoint | Status | Notes |
|-----------|--------|-------|
| 0A: Alpaca Stock Data | **PASS** | SIP feed, all OHLCV fields populated |
| 0A: Alpaca Options Chain | **PASS (limited)** | 342 contracts, bid/ask present, NO open interest |
| 0A: Alpaca Greeks | **FAIL** | Not available from Alpaca API — must use ThetaData or compute locally |
| 0B: ThetaData Greeks | **FAIL** | Terminal not running — start before Phase 1 |
| 0B: ThetaData OI/IV | **FAIL** | Terminal not running |
| 0B: ThetaData Historical | **FAIL** | Terminal not running |
| 0C: VIX (Yahoo Finance) | **PASS** | Current=29.70, 10-day history available, updates real-time |
| 0D: FinBERT Sentiment | **FAIL** | `transformers` library not installed |
| 0E: Order Execution | **PASS** | Paper account active, $5K funded, order lifecycle confirmed |

## Blockers Before Phase 1 Can Begin

1. **ThetaData Terminal must be started** — required for Greeks, OI, IV, and historical options data
2. **Install transformers + torch** — required for FinBERT sentiment scoring
3. **Greeks source decision** — Alpaca does not provide Greeks. ThetaData is the primary source. The fallback Black-Scholes computation works but is less accurate. The V2 "Greeks router" (always try ThetaData first, fall back to local BS) needs to be built.

## What Can Proceed Now

- Phase 1 data client for stock bars (Alpaca) and VIX (Yahoo Finance) can be built
- Phase 1 data client for options chains (Alpaca bid/ask) can be built
- Greeks router architecture can be designed (pending ThetaData testing)
- Order execution integration is confirmed working
