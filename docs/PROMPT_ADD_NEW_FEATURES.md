# CLAUDE CODE PROMPT — CATEGORY 3: ADD NEW FEATURES
# Priority: HIGH — These prevent systematic trading errors and improve edge quality
# Build each feature independently. Do not combine into a single large change.

---

## CONTEXT

This is an ML-driven options trading bot. Before making any changes, read these
files IN FULL — not snippets, every line:

  - strategies/base_strategy.py              (entry logic, _check_entries method)
  - ml/ev_filter.py                          (chain scanner, EVCandidate dataclass)
  - config.py                                (PRESET_DEFAULTS, all constants)
  - backend/routes/system.py                 (health endpoint)
  - backend/schemas.py                       (Pydantic models)
  - utils/circuit_breaker.py                 (existing pattern to follow)
  - data/alpaca_provider.py                  (AlpacaStockProvider, existing API usage)

---

## TASK OVERVIEW

Three new features. They are ordered by impact — implement them in order and
verify each one before starting the next.

---

## NEW FEATURE 1 — VOLATILITY REGIME FILTER (VIX GATE)

### Why This Matters
The bot currently trades whenever the ML signal and EV filter align, regardless
of macro volatility. VIX > 35 means bid-ask spreads blow out, IV spikes push
option prices to peak, and individual stock signals lose validity as correlations
collapse to 1. VIX < 13 means the market is in a low-volatility graveyard —
options are cheap but moves are small, and hitting a 50% profit target on a 7-DTE
swing option requires a large move that rarely happens in calm markets. Neither
environment offers real edge for this strategy.

### Files to Create/Modify

NEW FILE: `data/vix_provider.py`
MODIFY: `strategies/base_strategy.py` (add VIX check at Entry Step 1.5, between price fetch and bar fetch)
MODIFY: `config.py` (add VIX gate constants and preset config keys)

### Complete Code for data/vix_provider.py

```python
"""
VIX data provider — fetches current VIX level from Alpaca.
Used by base_strategy.py to gate entries based on volatility regime.

VIX is a market index. Alpaca provides it as a tradeable asset under
ticker "VIXY" (VIX ETF) or "^VIX" depending on the data feed.
We use the most recent daily close as a proxy for current VIX.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("options-bot.data.vix_provider")

# Cache VIX level for this many seconds before refetching
# During live trading this avoids an API call every 5-minute iteration
VIX_CACHE_TTL_SECONDS = 300  # 5 minutes


class VIXProvider:
    """
    Fetches current VIX level from Alpaca.
    Thread-safe with internal caching to avoid hammering the API.
    """

    def __init__(self):
        self._cached_vix: Optional[float] = None
        self._cache_time: float = 0.0
        logger.info("VIXProvider initialized")

    def get_current_vix(self) -> Optional[float]:
        """
        Return the current VIX level. Uses cached value if fresh.

        Returns:
            VIX level as float (e.g., 18.5), or None if unavailable.
            None is non-fatal — callers should allow trading when VIX is unavailable.
        """
        now = time.monotonic()

        # Return cached value if still fresh
        if self._cached_vix is not None and (now - self._cache_time) < VIX_CACHE_TTL_SECONDS:
            logger.debug(f"VIX cache hit: {self._cached_vix:.2f}")
            return self._cached_vix

        logger.info("Fetching VIX from Alpaca")
        t_start = time.time()

        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from config import ALPACA_API_KEY, ALPACA_API_SECRET

            client = StockHistoricalDataClient(
                api_key=ALPACA_API_KEY,
                secret_key=ALPACA_API_SECRET,
            )

            end = datetime.now(timezone.utc)
            start = end - timedelta(days=5)  # 5-day buffer for weekends/holidays

            request = StockBarsRequest(
                symbol_or_symbols="VIXY",
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
            )

            bars = client.get_stock_bars(request)
            if bars and "VIXY" in bars.data and bars.data["VIXY"]:
                vixy_close = float(bars.data["VIXY"][-1].close)
                # VIXY is an ETF that tracks VIX. Convert to approximate VIX level.
                # VIXY is NOT a 1:1 proxy. Its price is ~1/5 of VIX due to ETF structure.
                # Multiply by 5 as a rough approximation, or use directly with
                # appropriately scaled thresholds (see VIX_MIN_GATE, VIX_MAX_GATE in config.py).
                # We store the VIXY close directly and compare against VIXY-scaled thresholds.
                vix_level = vixy_close
                elapsed = time.time() - t_start
                logger.info(f"VIX (VIXY proxy) fetched: {vix_level:.2f} in {elapsed:.2f}s")

                self._cached_vix = vix_level
                self._cache_time = now
                return vix_level

        except Exception as e:
            logger.warning(
                f"VIX fetch failed (trading will continue without gate): {e}",
                exc_info=True
            )

        return None
```

**IMPORTANT**: After writing the above, verify whether Alpaca's SDK returns
`bars.data["VIXY"]` as a list or as a `BarSet`. Read `data/alpaca_provider.py`
to see how the existing code accesses bar data from the Alpaca SDK — use the
exact same pattern. Do NOT guess the API response structure.

### Changes to config.py

Add these constants at the bottom of the file, in their own section:

```python
# =============================================================================
# Volatility Regime Gate (VIX)
# Using VIXY (VIX ETF) as proxy. VIXY price ≈ VIX / 5.
# VIXY $3.00 ≈ VIX 15, VIXY $7.00 ≈ VIX 35
# =============================================================================
VIX_MIN_GATE = float(os.getenv("VIX_MIN_GATE", "3.0"))   # Don't trade below this VIXY level
VIX_MAX_GATE = float(os.getenv("VIX_MAX_GATE", "7.0"))   # Don't trade above this VIXY level
```

Add to all three presets in PRESET_DEFAULTS:
```python
"vix_gate_enabled": True,    # Set False to disable for testing
"vix_min": 3.0,              # VIXY proxy minimum (≈ VIX 15)
"vix_max": 7.0,              # VIXY proxy maximum (≈ VIX 35)
```

### Changes to strategies/base_strategy.py

Add `VIXProvider` initialization to `__init__`:

```python
from data.vix_provider import VIXProvider
self._vix_provider = VIXProvider()
```

In `_check_entries()`, add VIX gate as Entry Step 1.5 — after Step 1 (get current
price) and before Step 2 (get historical bars). Use this exact code:

```python
# ENTRY STEP 1.5: Volatility regime gate (VIX)
# Skip entries when macro volatility is outside the tradeable range.
# High VIX: spreads blow out, correlations collapse, signal loses validity.
# Low VIX: insufficient move magnitude to hit profit targets.
if self.config.get("vix_gate_enabled", True):
    vix_level = self._vix_provider.get_current_vix()
    if vix_level is not None:
        vix_min = self.config.get("vix_min", 3.0)
        vix_max = self.config.get("vix_max", 7.0)
        if not (vix_min <= vix_level <= vix_max):
            regime = "elevated" if vix_level > vix_max else "suppressed"
            logger.info(
                f"  ENTRY STEP 1.5 SKIP: Volatility regime {regime} "
                f"(VIXY={vix_level:.2f}, allowed={vix_min:.2f}-{vix_max:.2f})"
            )
            self._write_signal_log(
                underlying_price=underlying_price,
                step_stopped_at=1,
                stop_reason=f"VIX gate: VIXY={vix_level:.2f} outside [{vix_min},{vix_max}]",
            )
            return
        else:
            logger.info(
                f"  ENTRY STEP 1.5 OK: Volatility regime acceptable "
                f"(VIXY={vix_level:.2f})"
            )
    else:
        # VIX unavailable — allow trading (fail open, not closed)
        logger.warning("  ENTRY STEP 1.5: VIX unavailable — proceeding without gate")
```

---

## NEW FEATURE 2 — IMPLIED MOVE VS PREDICTED MOVE FILTER

### Why This Matters
Before entering any options position, the options market is already pricing in
an expected move through the ATM straddle. If the market implies an 8% weekly
move on TSLA and the ML model predicts 3%, there is no edge — the market has
already priced in a bigger move than the model expects. You are buying premium
at a price that assumes a larger move than you believe will happen.

Edge exists only when the model predicts a move that EXCEEDS the market's
implied move, meaning the model has identified directional conviction that the
market hasn't priced in directionally.

### Files to Modify

MODIFY: `ml/ev_filter.py` — add implied move calculation using existing chain data
MODIFY: `strategies/base_strategy.py` — check implied move before calling EV filter
MODIFY: `config.py` — add implied_move_gate config key to presets

### Changes to ml/ev_filter.py

Add a new standalone function BEFORE `scan_chain_for_best_ev`:

```python
def get_implied_move_pct(
    strategy,
    symbol: str,
    underlying_price: float,
    target_dte_min: int = 5,
    target_dte_max: int = 14,
) -> Optional[float]:
    """
    Estimate the market's implied move % by pricing the ATM straddle.
    
    An ATM straddle (buy ATM call + buy ATM put) costs approximately:
        straddle_cost = ATM_call_price + ATM_put_price
    
    The implied move % = straddle_cost / underlying_price * 100
    
    This represents the market's consensus on how much the stock could move
    over the straddle's remaining life. If the ML model predicts less than this,
    the market has already priced out the edge.
    
    Returns:
        Implied move as a percentage (e.g., 5.2 means ±5.2%), or None if unavailable.
    """
    from lumibot.entities import Asset

    logger.info(
        f"get_implied_move_pct: {symbol} price=${underlying_price:.2f} "
        f"DTE={target_dte_min}-{target_dte_max}"
    )

    try:
        chains = strategy.get_chains(Asset(symbol=symbol, asset_type="stock"))
        if not chains:
            logger.warning("get_implied_move_pct: no chains returned")
            return None

        today = strategy.get_datetime().date() if hasattr(strategy, "get_datetime") else \
            __import__("datetime").date.today()

        # Find the nearest expiration within the target DTE range
        target_exp = None
        target_dte = None
        for exp_str in sorted(chains.get("CALLS", {}).keys()):
            try:
                exp_date = __import__("datetime").date.fromisoformat(exp_str)
                dte = (exp_date - today).days
                if target_dte_min <= dte <= target_dte_max:
                    target_exp = exp_str
                    target_dte = dte
                    break
            except ValueError:
                continue

        if target_exp is None:
            logger.warning(
                f"get_implied_move_pct: no expiration in {target_dte_min}-{target_dte_max} DTE range"
            )
            return None

        # Find ATM call and put strikes
        call_strikes = sorted(chains.get("CALLS", {}).get(target_exp, []))
        put_strikes = sorted(chains.get("PUTS", {}).get(target_exp, []))

        if not call_strikes or not put_strikes:
            return None

        # ATM = closest strike to underlying price
        atm_call_strike = min(call_strikes, key=lambda s: abs(s - underlying_price))
        atm_put_strike = min(put_strikes, key=lambda s: abs(s - underlying_price))

        call_asset = Asset(
            symbol=symbol, asset_type="option",
            expiration=target_exp, strike=atm_call_strike, right="CALL"
        )
        put_asset = Asset(
            symbol=symbol, asset_type="option",
            expiration=target_exp, strike=atm_put_strike, right="PUT"
        )

        call_price = strategy.get_last_price(call_asset)
        put_price = strategy.get_last_price(put_asset)

        if call_price is None or put_price is None or call_price <= 0 or put_price <= 0:
            logger.warning("get_implied_move_pct: ATM option prices unavailable")
            return None

        straddle_cost = call_price + put_price
        implied_move_pct = (straddle_cost / underlying_price) * 100

        logger.info(
            f"get_implied_move_pct: {symbol} DTE={target_dte} "
            f"ATM call={atm_call_strike} @ ${call_price:.2f} "
            f"ATM put={atm_put_strike} @ ${put_price:.2f} "
            f"straddle=${straddle_cost:.2f} implied={implied_move_pct:.2f}%"
        )
        return implied_move_pct

    except Exception as e:
        logger.warning(f"get_implied_move_pct failed: {e}", exc_info=True)
        return None
```

### Changes to strategies/base_strategy.py

In `_check_entries()`, add implied move check as Entry Step 8.5 — after the PDT
check (Step 8) and before the EV filter scan (Step 9):

```python
# ENTRY STEP 8.5: Implied move vs predicted move gate
# Only enter if the model predicts a move that exceeds or approaches
# what the options market has already priced in.
# If the market implies a 6% weekly move and we predict 2%, there is no edge.
if self.config.get("implied_move_gate_enabled", True):
    from ml.ev_filter import get_implied_move_pct
    implied_move = get_implied_move_pct(
        strategy=self,
        symbol=self.symbol,
        underlying_price=underlying_price,
        target_dte_min=min_dte,
        target_dte_max=max_dte,
    )
    if implied_move is not None:
        abs_predicted = abs(predicted_return)
        # Require predicted move to be at least 80% of implied move
        implied_move_ratio_threshold = self.config.get("implied_move_ratio_min", 0.80)
        ratio = abs_predicted / implied_move if implied_move > 0 else 0
        if ratio < implied_move_ratio_threshold:
            logger.info(
                f"  ENTRY STEP 8.5 SKIP: Predicted move below implied move "
                f"(predicted={abs_predicted:.2f}% vs implied={implied_move:.2f}% "
                f"ratio={ratio:.2f} < {implied_move_ratio_threshold:.2f})"
            )
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                step_stopped_at=8,
                stop_reason=(
                    f"Implied move gate: predicted {abs_predicted:.2f}% "
                    f"< {implied_move_ratio_threshold:.0%} of implied {implied_move:.2f}%"
                ),
            )
            return
        else:
            logger.info(
                f"  ENTRY STEP 8.5 OK: Predicted {abs_predicted:.2f}% "
                f">= {implied_move_ratio_threshold:.0%} of implied {implied_move:.2f}%"
            )
    else:
        # Implied move unavailable — allow entry (fail open)
        logger.warning("  ENTRY STEP 8.5: Implied move unavailable — proceeding without gate")
```

### Changes to config.py

Add to all three presets in PRESET_DEFAULTS:

```python
"implied_move_gate_enabled": True,
"implied_move_ratio_min": 0.80,  # Predicted move must be >= 80% of market-implied move
```

---

## NEW FEATURE 3 — ALERT SYSTEM FOR CRITICAL EVENTS

### Why This Matters
The bot can be in crisis for hours without the user knowing: circuit breaker
OPEN, trading subprocess crashed, emergency stop loss hit, daily P&L below
threshold. A lightweight webhook-based alerter requires one file and hooks into
three existing code paths.

### Files to Create/Modify

NEW FILE: `utils/alerter.py`
MODIFY:   `strategies/base_strategy.py` (crash alert after 10 consecutive errors)
MODIFY:   `risk/risk_manager.py` (emergency stop loss alert)
MODIFY:   `config.py` (add ALERT_WEBHOOK_URL constant)
MODIFY:   `.env` (document new variable — do NOT write actual values)

### Complete Code for utils/alerter.py

```python
"""
Lightweight alert system for critical trading events.
Sends alerts via webhook (Discord, Slack, Pushover, etc.).

Configure by setting ALERT_WEBHOOK_URL in .env.
If not configured, alerts are logged but not sent — no crash.

Usage:
    from utils.alerter import send_alert
    send_alert("CRITICAL", "Circuit breaker OPEN on Theta Terminal", profile_id="abc123")
"""

import json
import logging
import threading
import time
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("options-bot.utils.alerter")


def send_alert(
    level: str,
    message: str,
    profile_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> bool:
    """
    Send an alert via configured webhook.

    Args:
        level:      "CRITICAL", "WARNING", or "INFO"
        message:    Human-readable alert message
        profile_id: Optional profile identifier for context
        details:    Optional dict of additional key-value context

    Returns:
        True if alert was sent successfully, False otherwise.
        Never raises — failures are logged and swallowed.
    """
    from config import ALERT_WEBHOOK_URL

    # Always log the alert regardless of webhook availability
    log_message = f"[ALERT:{level}]"
    if profile_id:
        log_message += f" [{profile_id}]"
    log_message += f" {message}"
    if details:
        log_message += f" | {details}"

    if level == "CRITICAL":
        logger.critical(log_message)
    elif level == "WARNING":
        logger.warning(log_message)
    else:
        logger.info(log_message)

    if not ALERT_WEBHOOK_URL:
        logger.debug("ALERT_WEBHOOK_URL not configured — alert logged only")
        return False

    # Send in background thread to never block the trading loop
    def _send():
        try:
            import urllib.request
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            payload_lines = [
                f"**[{level}] Options Bot Alert**",
                f"Time: {timestamp}",
            ]
            if profile_id:
                payload_lines.append(f"Profile: {profile_id}")
            payload_lines.append(f"Message: {message}")
            if details:
                for k, v in details.items():
                    payload_lines.append(f"{k}: {v}")

            # Discord/Slack compatible payload
            payload = json.dumps({"content": "\n".join(payload_lines)}).encode("utf-8")

            req = urllib.request.Request(
                ALERT_WEBHOOK_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    logger.warning(
                        f"Alert webhook returned status {resp.status}"
                    )
                else:
                    logger.debug("Alert sent successfully")
        except Exception as e:
            logger.warning(f"Alert send failed (non-fatal): {e}")

    t = threading.Thread(target=_send, daemon=True, name="alerter")
    t.start()
    return True
```

### Changes to config.py

Add to the backend/API section:

```python
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")  # Discord/Slack webhook URL
```

### Changes to strategies/base_strategy.py

Find the section where `_consecutive_errors` reaches 10 and the bot auto-pauses.
Import and call `send_alert` there:

```python
# In the outer except block where consecutive_errors >= 10:
from utils.alerter import send_alert
send_alert(
    level="CRITICAL",
    message=f"Bot auto-paused after 10 consecutive errors on {self.symbol}",
    profile_id=str(self.profile_id),
    details={"last_error": str(e), "consecutive_errors": self._consecutive_errors},
)
```

Also find `_export_circuit_state` (added in Category 2 Improvement 3) and call
`send_alert` when a circuit transitions to OPEN:

```python
# When theta_breaker.state == "OPEN":
send_alert(
    level="WARNING",
    message=f"Theta Terminal circuit breaker OPEN — bot in fail-fast mode",
    profile_id=str(self.profile_id),
)
```

### Changes to risk/risk_manager.py

Find the `check_emergency_stop_loss` method. After determining the emergency stop
is triggered, add:

```python
from utils.alerter import send_alert
send_alert(
    level="CRITICAL",
    message=f"Emergency stop loss triggered — trading halted",
    profile_id=profile_id,
    details={
        "portfolio_value": portfolio_value,
        "loss_pct": round(loss_pct, 2),
        "threshold_pct": EMERGENCY_STOP_LOSS_PCT,
    },
)
```

---

## AFTER MAKING ALL CHANGES, RUN THESE VERIFICATION COMMANDS

```bash
# 1. VIX provider imports cleanly
cd options-bot && python -c "
from data.vix_provider import VIXProvider, VIX_CACHE_TTL_SECONDS
v = VIXProvider()
print(f'PASS: VIXProvider initialized, cache TTL={VIX_CACHE_TTL_SECONDS}s')
"

# 2. Alerter imports and works without webhook configured
cd options-bot && python -c "
from utils.alerter import send_alert
result = send_alert('INFO', 'Test alert — no webhook configured', profile_id='test')
print(f'PASS: send_alert returned {result} (False expected when no webhook)')
"

# 3. EV filter has get_implied_move_pct function
cd options-bot && python -c "
import inspect
from ml.ev_filter import get_implied_move_pct, scan_chain_for_best_ev
sig = inspect.signature(get_implied_move_pct)
assert 'underlying_price' in sig.parameters
print('PASS: get_implied_move_pct exists in ev_filter.py')
"

# 4. Config has all new keys
cd options-bot && python -c "
from config import ALERT_WEBHOOK_URL, VIX_MIN_GATE, VIX_MAX_GATE, PRESET_DEFAULTS
assert isinstance(ALERT_WEBHOOK_URL, str)
assert isinstance(VIX_MIN_GATE, float)
assert isinstance(VIX_MAX_GATE, float)
for preset in ['swing', 'general', 'scalp']:
    cfg = PRESET_DEFAULTS[preset]
    assert 'vix_gate_enabled' in cfg, f'{preset} missing vix_gate_enabled'
    assert 'implied_move_gate_enabled' in cfg, f'{preset} missing implied_move_gate_enabled'
    assert 'implied_move_ratio_min' in cfg, f'{preset} missing implied_move_ratio_min'
print('PASS: all new config keys present')
"

# 5. base_strategy.py contains new entry steps
cd options-bot && python -c "
src = open('strategies/base_strategy.py').read()
assert 'ENTRY STEP 1.5' in src, 'VIX gate step 1.5 not found'
assert 'ENTRY STEP 8.5' in src, 'Implied move gate step 8.5 not found'
assert 'vix_provider' in src, '_vix_provider not initialized'
assert 'get_implied_move_pct' in src, 'implied move import not found'
print('PASS: new entry steps present in base_strategy.py')
"

# 6. Full import smoke test
cd options-bot && python -c "
import data.vix_provider
import utils.alerter
import ml.ev_filter
import strategies.base_strategy
import risk.risk_manager
import config
print('PASS: all modified and new modules import cleanly')
"
```

## SUCCESS CRITERIA
- All 6 verification commands print PASS with no exceptions
- No new pip dependencies added — urllib.request is stdlib, no install needed
- All three new features fail OPEN (allow trading) when their data source is unavailable
- Alert failures never crash the trading loop — the `send_alert` function must never raise

## FAILURE CRITERIA AND RECOVERY
If Alpaca's SDK response structure differs from what's written for VIXY:
  - Read data/alpaca_provider.py to see the exact pattern for accessing bar data
  - Mirror that exact pattern — do NOT guess field names
  - If VIXY is not available via Alpaca's stock endpoint, return None and log a warning

If `get_implied_move_pct` is too slow (>2 seconds) due to chain fetching:
  - Add a TTL cache using the same pattern as VIXProvider (store last result + timestamp)
  - TTL = 300 seconds (same as VIX)
  - Log "using cached implied move" when returning cached value
