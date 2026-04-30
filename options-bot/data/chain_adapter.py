"""Chain adapter — builds typed OptionChain instances from raw
UnifiedDataClient output for consumption by BasePreset.select_contract.

Concerns:
- Enumerates expirations in a DTE window via get_expirations
- Fetches raw chain dicts via get_options_chain
- Fetches per-contract greeks via get_greeks (bounded to ±5% NTM band)
- Translates casing (CALL/PUT -> call/put) and types (str -> date)
- Snapshots underlying price via get_stock_bars
- Returns one OptionChain per qualifying expiration

Pure orchestration glue. No preset-specific logic. Failures in any
single contract's greeks fetch are logged and that contract is
skipped — the adapter degrades to "fewer candidate contracts" rather
than failing the whole chain.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from data.unified_client import UnifiedDataClient
from profiles.base_preset import OptionChain, OptionContract

logger = logging.getLogger("options-bot.data.chain_adapter")

NTM_BAND_PCT = 0.05  # ±5% of underlying price for greeks-fetch eligibility


def expirations_in_dte_window(
    client: UnifiedDataClient,
    symbol: str,
    min_dte: int,
    max_dte: int,
    today: Optional[date] = None,
) -> list[tuple[str, date, int]]:
    """Return [(exp_str, exp_date, dte), ...] for expirations whose DTE
    from today is in [min_dte, max_dte] inclusive. Sorted by DTE
    ascending.

    Defensive: returns [] if client.get_expirations returns []. Bad
    date strings logged and skipped (not raised). today defaults to
    UTC today; pass for testability.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()

    try:
        raw = client.get_expirations(symbol)
    except Exception as e:
        logger.warning("get_expirations(%s) failed: %s", symbol, e)
        return []

    if not raw:
        return []

    out: list[tuple[str, date, int]] = []
    for exp_str in raw:
        try:
            exp_date = date.fromisoformat(exp_str)
        except (ValueError, TypeError) as e:
            logger.warning(
                "invalid expiration %r for %s: %s",
                exp_str, symbol, e,
            )
            continue
        dte = (exp_date - today).days
        if min_dte <= dte <= max_dte:
            out.append((exp_str, exp_date, dte))

    out.sort(key=lambda t: t[2])
    return out


def snapshot_underlying_price(
    client: UnifiedDataClient,
    symbol: str,
) -> Optional[float]:
    """Get current underlying price from latest 1-minute bar.

    Returns None on any exception (bars empty, network, etc.). Logs
    warning on failure. Idiom matches
    selection/selector.py:_get_underlying_price.
    """
    try:
        bars = client.get_stock_bars(symbol, "1Min", 1)
    except Exception as e:
        logger.warning(
            "snapshot_underlying_price(%s) failed: %s", symbol, e,
        )
        return None
    if bars is None or getattr(bars, "empty", False):
        logger.warning(
            "snapshot_underlying_price(%s): get_stock_bars returned empty",
            symbol,
        )
        return None
    try:
        return float(bars.iloc[-1]["close"])
    except Exception as e:
        logger.warning(
            "snapshot_underlying_price(%s) close-extract failed: %s",
            symbol, e,
        )
        return None


def build_option_contract(
    symbol: str,
    raw_dict: dict,
    expiration_str: str,
    expiration_date: date,
    greeks,
) -> OptionContract:
    """Construct one OptionContract from raw chain dict + OptionGreeks.

    Translations performed:
      - right: uppercase from raw -> lowercase for OptionContract
      - expiration: string -> datetime.date
      - delta: from greeks
      - iv: from greeks.implied_vol
      - bid, ask, mid, volume, open_interest: copied from raw_dict

    Defensive: missing keys for volume / open_interest default to 0.
    bid / ask / mid REQUIRED — KeyError if missing (an unusable
    contract should not silently turn into a Position downstream).
    """
    return OptionContract(
        symbol=symbol,
        right=raw_dict["right"].lower(),
        strike=float(raw_dict["strike"]),
        expiration=expiration_date,
        bid=float(raw_dict["bid"]),
        ask=float(raw_dict["ask"]),
        mid=float(raw_dict["mid"]),
        delta=float(greeks.delta),
        iv=float(greeks.implied_vol),
        open_interest=int(raw_dict.get("open_interest", 0)),
        volume=int(raw_dict.get("volume", 0)),
    )


def build_option_chain(
    client: UnifiedDataClient,
    symbol: str,
    expiration_str: str,
    expiration_date: date,
    right_filter: str,
    underlying_price: Optional[float] = None,
) -> Optional[OptionChain]:
    """Build one typed OptionChain for a single expiration.

    See module docstring for the procedure. Returns None only if the
    underlying price cannot be obtained or the raw chain fetch raises.
    Returns an empty-contracts OptionChain when raw chain is empty or
    every greeks call fails (degraded, not failed).
    """
    if underlying_price is None:
        underlying_price = snapshot_underlying_price(client, symbol)
        if underlying_price is None:
            logger.warning(
                "build_option_chain(%s, %s): no underlying price",
                symbol, expiration_str,
            )
            return None

    try:
        raw_chain = client.get_options_chain(symbol, expiration_str)
    except Exception as e:
        logger.warning(
            "get_options_chain(%s, %s) failed: %s",
            symbol, expiration_str, e,
        )
        return None

    snapshot_time = datetime.now(timezone.utc)

    if not raw_chain:
        return OptionChain(
            symbol=symbol,
            underlying_price=underlying_price,
            contracts=[],
            snapshot_time=snapshot_time,
        )

    right_upper = right_filter.upper()
    low = underlying_price * (1.0 - NTM_BAND_PCT)
    high = underlying_price * (1.0 + NTM_BAND_PCT)

    candidates: list[dict] = []
    for raw in raw_chain:
        if raw.get("right", "").upper() != right_upper:
            continue
        strike = raw.get("strike")
        if strike is None or not (low <= strike <= high):
            continue
        if raw.get("bid", 0) <= 0 or raw.get("ask", 0) <= 0:
            continue
        candidates.append(raw)

    contracts: list[OptionContract] = []
    for raw in candidates:
        try:
            greeks = client.get_greeks(
                symbol, expiration_str, raw["strike"], right_upper,
            )
        except Exception as e:
            logger.warning(
                "get_greeks(%s, %s, %s, %s) failed: %s",
                symbol, expiration_str, raw["strike"], right_upper, e,
            )
            continue
        try:
            oc = build_option_contract(
                symbol, raw, expiration_str, expiration_date, greeks,
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(
                "build_option_contract(%s, strike=%s) failed: %s",
                symbol, raw.get("strike"), e,
            )
            continue
        contracts.append(oc)

    return OptionChain(
        symbol=symbol,
        underlying_price=underlying_price,
        contracts=contracts,
        snapshot_time=snapshot_time,
    )
