"""Phase 1a SwingPreset — multi-day directional swing trades on liquid
mid/large caps. Implements ARCHITECTURE.md §4.1 entry path. Contract
selection (B3) and exit logic (B4) added in subsequent prompts.

Entry AND-gate (per §4.1, post commits 549b7a4 and 0e4a933):
  1. Setup type ∈ {momentum, compression_breakout, macro_trend}
  2. Setup score ≥ MIN_SETUP_SCORE
  3. Setup direction is "bullish" or "bearish" (not "neutral")
  4. VIX ∈ [VIX_MIN, VIX_MAX] inclusive
  5. IVR < IVR_MAX (skipped when fetcher returns None — cold-start)
  6. No HIGH-impact macro event within MACRO_LOOKAHEAD_MINUTES

Dependency injection: ivr_fetcher and macro_fetcher are passed at
construction so tests can stub them. Production wire-in supplies
the IVR fetcher (returning 0-100 or None on cold-start) and the
macro event fetcher (returning a list of events with impact_level).
This module deliberately does not pull those callables in by name —
the orchestrator owns the wire-in so the seam stays clean.
"""

from __future__ import annotations

import logging
from typing import Optional

from market.context import MarketSnapshot
from profiles.base_preset import (
    BasePreset,
    ContractSelection,
    EntryDecision,
    ExitDecision,
    OptionChain,
    Position,
    ProfileState,
)
from profiles.profile_config import ProfileConfig
from scanner.setups import SetupScore

logger = logging.getLogger("options-bot.profiles.swing")


class SwingPreset(BasePreset):
    """Phase 1a swing preset — see ARCHITECTURE.md §4.1.

    Entry: scanner setup score (momentum / compression_breakout /
    macro_trend) in intended direction at score ≥ min, VIX 13-30,
    IVR < 80 (skipped if cold), no HIGH-impact macro event within 48h.

    This class currently implements evaluate_entry only.
    select_contract and evaluate_exit raise NotImplementedError
    pending B3 and B4.
    """

    name = "swing"
    accepted_setup_types = frozenset({
        "momentum", "compression_breakout", "macro_trend",
    })

    VIX_MIN = 13.0
    VIX_MAX = 30.0
    IVR_MAX = 80.0
    MACRO_LOOKAHEAD_MINUTES = 2880  # 48 hours
    MIN_SETUP_SCORE = 0.35

    DELTA_MIN = 0.40
    DELTA_MAX = 0.55
    DELTA_TARGET = 0.50
    MAX_SPREAD_PCT_OF_MID = 0.04
    MIN_OPEN_INTEREST = 500
    MIN_CONTRACT_VOLUME = 100

    def __init__(
        self,
        config: ProfileConfig,
        ivr_fetcher=None,
        macro_fetcher=None,
    ):
        """ivr_fetcher and macro_fetcher are dependency-injected callables
        so tests can stub them. Production wire-in passes
        scoring.ivr.get_ivr and macro.reader.get_active_events.

        ivr_fetcher signature: (symbol: str) -> Optional[float]
            Returns IVR on a 0-100 scale, or None on cold-start /
            data outage.

        macro_fetcher signature:
            (symbol: str, lookahead_minutes: int) -> list
            Each list item must expose impact_level: str
            ("HIGH" / "MEDIUM" / "LOW").
        """
        super().__init__(config)
        self._ivr_fetcher = ivr_fetcher
        self._macro_fetcher = macro_fetcher

    def is_active_now(self, market: MarketSnapshot) -> bool:
        """Swing has no time-of-day gate. Trades during regular market
        hours. The orchestrator is responsible for not calling this
        outside RTH.
        """
        return True

    def evaluate_entry(
        self,
        symbol: str,
        scanner_output: SetupScore,
        market: MarketSnapshot,
        state: ProfileState,
    ) -> EntryDecision:
        """AND-gate evaluation per ARCHITECTURE.md §4.1.

        Returns EntryDecision(should_enter=False, reason=...) on the
        first failed gate. Returns EntryDecision(should_enter=True, ...)
        only if all gates pass.

        IVR cold-start: when ivr_fetcher returns None, the IVR<80 check
        is SKIPPED (not failed) and the reason field of a successful
        entry records "IVR unavailable — check skipped". The remaining
        volatility gate (VIX 13-30) continues to enforce.
        """
        setup = scanner_output

        # (a) Setup type
        if setup.setup_type not in self.accepted_setup_types:
            return EntryDecision(
                should_enter=False,
                reason=f"setup_type {setup.setup_type!r} not accepted",
                direction=setup.direction,
            )

        # (b) Setup score floor
        if setup.score < self.MIN_SETUP_SCORE:
            return EntryDecision(
                should_enter=False,
                reason=(
                    f"setup score {setup.score:.3f} below min "
                    f"{self.MIN_SETUP_SCORE}"
                ),
                direction=setup.direction,
            )

        # (c) Direction must be directional (not neutral)
        if setup.direction not in ("bullish", "bearish"):
            return EntryDecision(
                should_enter=False,
                reason="setup direction neutral — no directional entry",
                direction=setup.direction,
            )

        # (d) VIX regime
        if not (self.VIX_MIN <= market.vix_level <= self.VIX_MAX):
            return EntryDecision(
                should_enter=False,
                reason=(
                    f"VIX {market.vix_level:.2f} outside "
                    f"[{self.VIX_MIN}, {self.VIX_MAX}]"
                ),
                direction=setup.direction,
            )

        # (e) IVR check (skip-and-log on None per §4.1 IVR cold-start note)
        if self._ivr_fetcher is None:
            ivr_note = "IVR fetcher not configured"
        else:
            ivr = self._ivr_fetcher(symbol)
            if ivr is None:
                logger.info(
                    "swing IVR unavailable for %s — check skipped", symbol,
                )
                ivr_note = "IVR unavailable — check skipped"
            elif ivr >= self.IVR_MAX:
                return EntryDecision(
                    should_enter=False,
                    reason=f"IVR {ivr:.1f} >= max {self.IVR_MAX}",
                    direction=setup.direction,
                )
            else:
                ivr_note = f"IVR {ivr:.1f}"

        # (f) Macro event window (HIGH-impact within 48h)
        if self._macro_fetcher is None:
            macro_note = "macro fetcher not configured"
        else:
            events = self._macro_fetcher(
                symbol, self.MACRO_LOOKAHEAD_MINUTES,
            )
            high_events = [
                e for e in events if getattr(e, "impact_level", None) == "HIGH"
            ]
            if high_events:
                return EntryDecision(
                    should_enter=False,
                    reason=(
                        f"HIGH-impact macro event within 48h "
                        f"({len(high_events)} event(s))"
                    ),
                    direction=setup.direction,
                )
            macro_note = "no HIGH-impact events within 48h"

        # (g) All gates passed
        return EntryDecision(
            should_enter=True,
            reason=(
                f"swing entry: {setup.setup_type} score={setup.score:.3f} "
                f"dir={setup.direction}; VIX={market.vix_level:.2f}; "
                f"{ivr_note}; {macro_note}"
            ),
            direction=setup.direction,
        )

    def select_contract(
        self,
        symbol: str,
        direction: str,
        chain: OptionChain,
    ) -> Optional[ContractSelection]:
        """Pick the best NTM contract from a typed OptionChain.

        Translates direction → option side, applies liquidity gates
        (spread/mid ≤ 4%, OI ≥ 500, volume ≥ 100), filters by delta
        band [0.40, 0.55] (signed for calls, |delta| for puts), and
        returns the survivor closest to delta 0.50. Ties broken by
        tighter spread, then higher open interest.

        Note on §4.1's "walk one strike if delta < 0.40" prose: this
        implementation evaluates the chain's pre-fetched NTM band
        (chain_adapter fetches greeks for the ±5% strike window)
        exhaustively and picks the best by |delta - 0.50|. For
        vanilla options where delta is monotonic in strike, this is
        functionally equivalent to the walking algorithm and simpler
        to reason about.

        Returns None if direction is non-directional, the right-side
        chain is empty, or no contract clears every gate.
        """
        # (a) Translate direction → right
        if direction == "bullish":
            right = "call"
        elif direction == "bearish":
            right = "put"
        else:
            logger.warning(
                "select_contract called with non-directional "
                "direction=%r — returning None", direction,
            )
            return None

        # (b) Filter by right
        same_right = [c for c in chain.contracts if c.right == right]
        if not same_right:
            return None

        # (c) Liquidity gates
        after_liq: list[tuple] = []
        for c in same_right:
            if c.mid <= 0:
                logger.debug(
                    "drop %s strike=%s: mid=%s (non-positive)",
                    symbol, c.strike, c.mid,
                )
                continue
            spread_pct = (c.ask - c.bid) / c.mid
            if spread_pct > self.MAX_SPREAD_PCT_OF_MID:
                logger.debug(
                    "drop %s strike=%s: spread_pct=%.4f > %.4f",
                    symbol, c.strike, spread_pct,
                    self.MAX_SPREAD_PCT_OF_MID,
                )
                continue
            if c.open_interest < self.MIN_OPEN_INTEREST:
                logger.debug(
                    "drop %s strike=%s: OI=%d < %d",
                    symbol, c.strike, c.open_interest,
                    self.MIN_OPEN_INTEREST,
                )
                continue
            if c.volume < self.MIN_CONTRACT_VOLUME:
                logger.debug(
                    "drop %s strike=%s: volume=%d < %d",
                    symbol, c.strike, c.volume,
                    self.MIN_CONTRACT_VOLUME,
                )
                continue
            after_liq.append((c, spread_pct))

        # (d) Delta band
        after_delta: list[tuple] = []
        for c, spread_pct in after_liq:
            if right == "call":
                if not (self.DELTA_MIN <= c.delta <= self.DELTA_MAX):
                    logger.debug(
                        "drop %s strike=%s: call delta=%.3f outside [%.2f, %.2f]",
                        symbol, c.strike, c.delta,
                        self.DELTA_MIN, self.DELTA_MAX,
                    )
                    continue
            else:
                abs_delta = abs(c.delta)
                if not (self.DELTA_MIN <= abs_delta <= self.DELTA_MAX):
                    logger.debug(
                        "drop %s strike=%s: put |delta|=%.3f outside [%.2f, %.2f]",
                        symbol, c.strike, abs_delta,
                        self.DELTA_MIN, self.DELTA_MAX,
                    )
                    continue
            after_delta.append((c, spread_pct))

        if not after_delta:
            logger.info(
                "no qualifying contract for %s %s in chain (snapshot %s)",
                symbol, right, chain.snapshot_time,
            )
            return None

        # (e) Pick winner: minimize |abs(delta) - DELTA_TARGET|;
        # ties broken by tighter spread, then higher OI.
        def _sort_key(item):
            c, sp = item
            delta_dist = abs(abs(c.delta) - self.DELTA_TARGET)
            return (delta_dist, sp, -c.open_interest)

        after_delta.sort(key=_sort_key)
        winner, _ = after_delta[0]

        # (g) Construct ContractSelection
        today = chain.snapshot_time.date()
        dte = (winner.expiration - today).days
        return ContractSelection(
            symbol=symbol,
            right=right,
            strike=winner.strike,
            expiration=winner.expiration,
            target_delta=self.DELTA_TARGET,
            estimated_premium=winner.mid,
            dte=dte,
        )

    def evaluate_exit(
        self,
        position: Position,
        current_quote: float,
        market: MarketSnapshot,
    ) -> ExitDecision:
        raise NotImplementedError(
            "evaluate_exit is added in Prompt B4"
        )
