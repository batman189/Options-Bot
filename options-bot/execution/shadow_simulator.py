"""Shadow execution simulator.

Drives the strategy's normal on_filled_order callback with synthetic
fill events constructed from real market quotes. Used when
config.EXECUTION_MODE == "shadow" so the bot can validate strategy
end-to-end against live market data without submitting any orders to
a broker — necessary while the $5k paper account is PDT-restricted.

Design notes (investigation Steps 2 and 5):

  * on_filled_order reads only two attributes off the order object:
    .side (string like "buy_to_open" / "sell_to_close") and
    .identifier (the string used as the key into _trade_id_map).
    The synthetic SyntheticOrder carries both, plus .quantity /
    .filled_price / .status / .asset / .symbol so downstream UI and
    any future callback extensions see a Lumibot-compatible shape.

  * The strategy's three Lumibot callbacks are on_filled_order,
    on_canceled_order, on_error_order. In shadow mode only the first
    fires — synthetic fills never cancel or error. The "shadow-"
    identifier prefix is idempotent with the Prompt 34 "invalid-id-"
    pattern so the _trade_id_map pop in the cancel/error callbacks
    no-ops safely if shadow IDs ever do leak into them.

  * Dispatch is SYNCHRONOUS from the caller's perspective — we drive
    on_filled_order inline, which contrasts with live mode where
    Lumibot enqueues an event and the callback fires later. Callers
    must have written _trade_id_map and _last_entry_time BEFORE
    invoking submit_entry so on_filled_order sees a consistent state
    during dispatch. v2_strategy handles that ordering.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("options-bot.execution.shadow")


@dataclass
class SyntheticPosition:
    """Minimal position wrapper fed to on_filled_order.

    on_filled_order reads only .asset off the position (for the log
    line). The trade_manager.add_position call uses entry["symbol"],
    entry["strike"], etc. from the _trade_id_map entry, not the
    position here. This class stays small on purpose.
    """

    asset: Any


@dataclass
class SyntheticOrder:
    """Synthetic Lumibot-compatible order for shadow fills.

    Field list mirrors the attributes on_filled_order / _alpaca_id
    read today. Kept as dataclass so the schema is obvious — adding a
    field is a one-line change if a future Lumibot callback consumer
    needs it.
    """

    identifier: str
    side: str
    quantity: int
    filled_price: float
    asset: Any
    symbol: str
    status: str = "filled"
    # Placeholder for future broker parity — callers can extend
    # without touching the simulator.
    extras: dict = field(default_factory=dict)


class ShadowSimulator:
    """Simulates order submission and fills using real market quotes.

    Used when EXECUTION_MODE=shadow. Drives the bot's normal
    on_filled_order callback with synthetic fill events so downstream
    logic (trade manager, signal logs, learning) operates identically
    to live mode.

    Does NOT simulate: broker latency, partial fills, queue position,
    network errors. Fills always happen at the current quote,
    instantly. P&L will be optimistic relative to real execution —
    tune SHADOW_FILL_SLIPPAGE_PCT after a week of shadow data has
    calibrated realistic spread assumptions.
    """

    def __init__(self, strategy_ref, quote_fetcher: Callable[[Any], Optional[float]]):
        """
        Args:
            strategy_ref: the V2Strategy instance (for callback dispatch).
            quote_fetcher: callable that returns the current mark price
                for a Lumibot Asset, normally self.get_last_price.
                Must return None or <=0 when the quote is unavailable —
                the simulator refuses to fake fills in that case.
        """
        self._strategy = strategy_ref
        self._get_quote = quote_fetcher

    def submit_entry(
        self,
        order,
        profile_name: str,
        trade_id: str,
        preassigned_id: Optional[str] = None,
    ) -> Optional[str]:
        """Simulate a buy_to_open fill.

        Returns the synthetic order identifier on success (string
        starting with "shadow-"). Returns None when the quote is
        unavailable so the caller can map to a block_reason — we
        never fake fills.

        preassigned_id: caller-supplied shadow id. v2_strategy uses
        this to pre-seed _trade_id_map BEFORE dispatching, so the
        synchronous on_filled_order call pops the correct entry. If
        None, the simulator generates its own id.
        """
        return self._simulate(
            order=order,
            side="buy_to_open",
            trade_id=trade_id,
            profile_name=profile_name,
            slippage_sign=+1,  # buys pay mid * (1 + pct)
            log_prefix="SHADOW: ENTRY",
            preassigned_id=preassigned_id,
        )

    def submit_exit(
        self,
        order,
        trade_id: str,
        preassigned_id: Optional[str] = None,
    ) -> Optional[str]:
        """Simulate a sell_to_close fill.

        Returns the synthetic order identifier on success. Returns
        None when the quote is unavailable. preassigned_id: see
        submit_entry docstring.
        """
        return self._simulate(
            order=order,
            side="sell_to_close",
            trade_id=trade_id,
            profile_name=None,
            slippage_sign=-1,  # sells receive mid * (1 - pct)
            log_prefix="SHADOW: EXIT",
            preassigned_id=preassigned_id,
        )

    def _simulate(
        self,
        order,
        side: str,
        trade_id: str,
        profile_name: Optional[str],
        slippage_sign: int,
        log_prefix: str,
        preassigned_id: Optional[str] = None,
    ) -> Optional[str]:
        # Imported lazily so unit tests can reload config without
        # holding a stale slippage value from module-import time.
        import config

        asset = getattr(order, "asset", None)
        quantity = int(getattr(order, "quantity", 0)) or 0

        quote = None
        try:
            quote = self._get_quote(asset)
        except Exception as exc:
            logger.warning(
                f"{log_prefix}: quote fetch raised "
                f"{type(exc).__name__}: {exc} — treating as unavailable"
            )
            quote = None

        if quote is None or quote <= 0:
            logger.warning(
                f"{log_prefix}: quote unavailable for {trade_id[:8]} "
                f"(asset={getattr(asset, 'symbol', '?')}, raw={quote!r}) "
                "— refusing to fake fill"
            )
            return None

        slippage_pct = float(getattr(config, "SHADOW_FILL_SLIPPAGE_PCT", 0.0))
        fill_price = round(quote * (1.0 + slippage_sign * slippage_pct / 100.0), 4)

        shadow_id = preassigned_id if preassigned_id else f"shadow-{uuid.uuid4()}"
        synthetic_order = SyntheticOrder(
            identifier=shadow_id,
            side=side,
            quantity=quantity,
            filled_price=fill_price,
            asset=asset,
            symbol=getattr(asset, "symbol", ""),
        )
        synthetic_position = SyntheticPosition(asset=asset)

        profile_bit = f" profile={profile_name}" if profile_name else ""
        logger.info(
            f"{log_prefix} {trade_id[:8]} {side} "
            f"qty={quantity} quote=${quote:.4f} "
            f"slippage={slippage_pct:.2f}% fill=${fill_price:.4f}"
            f"{profile_bit} id={shadow_id[:16]}..."
        )

        # Dispatch the fill callback. The map write / cooldown set in
        # v2_strategy must run BEFORE this call — the callback reads
        # _trade_id_map to resolve trade metadata. See module docstring.
        self._strategy.on_filled_order(
            synthetic_position, synthetic_order, fill_price, quantity, 100
        )
        return shadow_id
