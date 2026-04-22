"""Options contract selector — strike tier by confidence, expiration by profile,
liquidity gate (fixed: OI>200, vol>50, spread<15%), optional EV validation
(disabled by default per Prompt 17 Commit B; see filters.apply_ev_validation
docstring), then rank by tightest spread among qualifying contracts."""

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

from selection.expiration import select_expiration
from selection.filters import apply_liquidity_gate, apply_ev_validation

logger = logging.getLogger("options-bot.selection")

@dataclass
class SelectedContract:
    """The contract chosen for trading."""
    symbol: str
    strike: float
    expiration: str       # "YYYY-MM-DD"
    right: str            # "CALL" or "PUT"
    bid: float
    ask: float
    mid: float
    spread_pct: float
    open_interest: int
    volume: int
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_vol: float
    ev_pct: Optional[float]   # None when EV gate was disabled (Prompt 17 Commit B)
    strike_tier: str      # "itm", "atm", "otm"


class OptionsSelector:
    """Selects the best contract given a trade decision."""

    def __init__(self, data_client=None):
        self._client = data_client

    def select(
        self,
        symbol: str,
        direction: str,       # "bullish" or "bearish"
        confidence: float,
        hold_minutes: int,
        profile_name: str,
        predicted_move_pct: Optional[float] = None,
        use_otm: bool = False,
        config: dict = None,
    ) -> Optional[SelectedContract]:
        """Select a contract. Returns None if no qualifying contract.

        Ranking criterion: among contracts that pass liquidity gate (OI>200,
        vol>50, spread<15%) and EV validation (EV>0%), select the one with
        the tightest bid-ask spread. Tightest spread minimizes entry/exit cost
        and correlates with highest market maker activity. Single criterion —
        no composite needed when pre-filters are strict.
        """
        if self._client is None:
            from data.unified_client import UnifiedDataClient
            self._client = UnifiedDataClient()

        right = "CALL" if direction == "bullish" else "PUT"
        underlying = self._get_underlying_price(symbol)
        if underlying is None:
            logger.warning(f"Selector: no underlying price for {symbol}")
            return None

        # Step 1: Determine expiration (moved up for DTE calculation)
        expiration = select_expiration(profile_name, config=config or {})
        if expiration is None:
            logger.warning(f"Selector: no valid expiration for {profile_name}")
            return None
        dte = (datetime.strptime(expiration, "%Y-%m-%d").date() - date.today()).days

        # Step 2: Determine strike tier
        tier = self._strike_tier(confidence, use_otm=use_otm)
        if dte == 0:
            if use_otm:
                tier = "otm"
                logger.info("Selector: OTM tier for 0DTE scalp")
            else:
                tier = "atm"
                logger.info("Selector: ATM tier for 0DTE non-scalp")

        # Step 3: Fetch chain and filter
        try:
            chain = self._client.get_options_chain(symbol, expiration)
        except Exception as e:
            logger.warning(f"Selector: chain fetch failed: {e}")
            return None

        # Step 4: Filter to correct right + strike tier
        target_strike = self._target_strike(underlying, tier, right)
        candidates = self._filter_chain(chain, right, target_strike, underlying, tier)

        if not candidates:
            logger.info(f"Selector: no candidates for {symbol} {right} {tier} exp={expiration}")
            return None

        # Step 5: Liquidity gate (non-configurable)
        liquid = apply_liquidity_gate(candidates, symbol=symbol, dte=dte)
        if not liquid:
            logger.info(f"Selector: no contracts pass liquidity gate for {symbol}")
            return None

        # Step 6: EV validation + Greeks
        hold_days = hold_minutes / (60 * 24)
        validated = apply_ev_validation(
            liquid, self._client, symbol, expiration, right, underlying,
            predicted_move_pct, hold_days, dte,
        )
        if not validated:
            logger.info(f"Selector: no contracts pass EV validation for {symbol}")
            return None

        # Step 7: Rank by tightest spread, build SelectedContract
        best_c = min(validated, key=lambda c: c["_spread_pct"])
        g = best_c["_greeks"]
        stier = self._strike_tier_for_contract(best_c["strike"], underlying, right)
        best = SelectedContract(
            symbol=symbol, strike=best_c["strike"], expiration=expiration, right=right,
            bid=best_c.get("bid", 0), ask=best_c.get("ask", 0), mid=best_c["_mid"],
            spread_pct=best_c["_spread_pct"], open_interest=best_c.get("open_interest", 0),
            volume=best_c.get("volume", 0), delta=g.delta, gamma=g.gamma,
            theta=g.theta, vega=g.vega, implied_vol=g.implied_vol,
            ev_pct=best_c["_ev_pct"], strike_tier=stier,
        )
        ev_str = f"{best.ev_pct:.1f}%" if best.ev_pct is not None else "disabled"
        logger.info(
            f"Selector: {symbol} {right} ${best.strike} exp={expiration} "
            f"mid=${best.mid:.2f} spread={best.spread_pct:.1f}% "
            f"EV={ev_str} tier={stier}"
        )
        return best

    def _strike_tier(self, confidence: float, use_otm: bool = False) -> str:
        """Map confidence to strike tier.

        For OTM scalp strategies, the confidence-tier mapping is bypassed —
        always return otm regardless of confidence. The lotto-ticket thesis
        wants cheap contracts in size, not ITM safety.

        For swing/momentum profiles, even high confidence maps to ATM, not
        ITM — ITM options cost more, fill worse, and give worse leverage on
        small accounts. ITM is almost never right for this strategy.
        """
        if use_otm:
            return "otm"
        if confidence >= 0.80:
            return "atm"
        elif confidence >= 0.65:
            return "atm"
        else:
            return "otm"

    def _target_strike(self, underlying: float, tier: str, right: str) -> float:
        """Compute target strike price for the tier."""
        # SPY strikes are $1 apart, TSLA $2.50-5 apart
        # For ITM: one strike inside the money
        # For ATM: nearest to underlying
        # For OTM: one strike outside the money
        step = 1.0 if underlying > 500 else 2.5  # Rough step size
        if tier == "atm":
            return round(underlying / step) * step
        elif tier == "itm":
            if right == "CALL":
                return round((underlying - step) / step) * step
            else:
                return round((underlying + step) / step) * step
        else:  # otm
            # 0.5% OTM target: far enough to be cheap ($0.20-0.60 premiums for
            # SPY 0DTE), close enough to go ITM on a real move. Single-step
            # OTM (~$1 for SPY) was still pricing at $1.50+ — not a lotto ticket.
            # Example: SPY $570 -> 0.5% = $2.85 -> PUT $568, CALL $573.
            otm_distance = round(underlying * 0.005 / step) * step
            otm_distance = max(step * 2, otm_distance)  # minimum 2 strikes out
            if right == "CALL":
                return round((underlying + otm_distance) / step) * step
            else:
                return round((underlying - otm_distance) / step) * step

    def _filter_chain(self, chain: list[dict], right: str, target_strike: float,
                       underlying: float, tier: str) -> list[dict]:
        """Filter chain to contracts matching right, near target strike,
        and respecting moneyness direction for the requested tier."""
        tolerance = 3.0 if underlying > 500 else 5.0
        filtered = []
        for c in chain:
            if c.get("right", "").upper() != right:
                continue
            strike = c.get("strike", 0)
            if abs(strike - target_strike) > tolerance:
                continue
            bid = c.get("bid", 0)
            ask = c.get("ask", 0)
            if bid <= 0 or ask <= 0 or ask < bid:
                continue
            # Enforce moneyness direction: OTM must actually be out of the money,
            # ITM must actually be in the money. Prevents tolerance from crossing ATM.
            if tier == "otm":
                if right == "CALL" and strike <= underlying:
                    continue  # CALL OTM requires strike > underlying
                if right == "PUT" and strike >= underlying:
                    continue  # PUT OTM requires strike < underlying
            elif tier == "itm":
                if right == "CALL" and strike >= underlying:
                    continue  # CALL ITM requires strike < underlying
                if right == "PUT" and strike <= underlying:
                    continue  # PUT ITM requires strike > underlying
            filtered.append(c)
        return filtered

    def _strike_tier_for_contract(self, strike: float, underlying: float, right: str) -> str:
        """Classify a contract's moneyness."""
        if right == "CALL":
            if strike < underlying:
                return "itm"
            elif abs(strike - underlying) / underlying < 0.005:
                return "atm"
            else:
                return "otm"
        else:
            if strike > underlying:
                return "itm"
            elif abs(strike - underlying) / underlying < 0.005:
                return "atm"
            else:
                return "otm"

    def _get_underlying_price(self, symbol: str) -> Optional[float]:
        """Get current price from most recent bar."""
        try:
            bars = self._client.get_stock_bars(symbol, "1Min", 1)
            return float(bars.iloc[-1]["close"])
        except Exception as e:
            logger.warning(f"Underlying price failed for {symbol}: {e}")
            return None
