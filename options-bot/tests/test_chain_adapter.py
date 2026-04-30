"""Unit tests for data.chain_adapter.

Mocks UnifiedDataClient so no network calls. Mirrors the unittest.mock
pattern in tests/test_unified_client_expirations.py.

Run via:
    python -m pytest tests/test_chain_adapter.py -v
"""

import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.chain_adapter import (  # noqa: E402
    NTM_BAND_PCT,
    build_option_chain,
    build_option_contract,
    expirations_in_dte_window,
    prefer_symbol_specific_expirations,
    snapshot_underlying_price,
)
from data.unified_client import OptionGreeks  # noqa: E402
from profiles.base_preset import OptionChain, OptionContract  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────


def _mock_client(
    expirations=None,
    chain=None,
    greeks=None,
    bars=None,
):
    """Build a MagicMock UnifiedDataClient with the four methods stubbed.

    Pass a value to set return_value, or a callable / Exception to set
    side_effect.
    """
    client = MagicMock()

    def _wire(method, value):
        if isinstance(value, Exception):
            method.side_effect = value
        elif callable(value) and not isinstance(value, MagicMock):
            method.side_effect = value
        else:
            method.return_value = value

    if expirations is not None:
        _wire(client.get_expirations, expirations)
    if chain is not None:
        _wire(client.get_options_chain, chain)
    if greeks is not None:
        _wire(client.get_greeks, greeks)
    if bars is not None:
        _wire(client.get_stock_bars, bars)
    return client


def _raw_contract(
    strike: float,
    right: str = "CALL",
    bid: float = 1.00,
    ask: float = 1.10,
    volume: int = 100,
    open_interest: int = 500,
) -> dict:
    """Match the dict shape get_options_chain returns. Right is UPPERCASE."""
    mid = round((bid + ask) / 2, 4) if bid and ask else 0
    return {
        "strike": strike,
        "right": right,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "volume": volume,
        "open_interest": open_interest,
    }


def _greeks(
    delta: float = 0.45,
    iv: float = 0.25,
    underlying_price: float = 500.0,
) -> OptionGreeks:
    return OptionGreeks(
        delta=delta,
        gamma=0.01,
        theta=-0.05,
        vega=0.10,
        rho=0.02,
        implied_vol=iv,
        underlying_price=underlying_price,
        source="test",
    )


def _bars_df(close_price: float):
    return pd.DataFrame([{
        "open": close_price,
        "high": close_price,
        "low": close_price,
        "close": close_price,
        "volume": 100_000,
    }])


# ─────────────────────────────────────────────────────────────────
# expirations_in_dte_window
# ─────────────────────────────────────────────────────────────────


def test_expirations_empty_input_returns_empty():
    client = _mock_client(expirations=[])
    out = expirations_in_dte_window(client, "SPY", 7, 14)
    assert out == []


def test_expirations_window_matches_two_of_five_sorted_asc():
    """today=2026-01-01, window [7,14], expirations with DTEs 3, 5, 8, 12, 20."""
    today = date(2026, 1, 1)
    client = _mock_client(expirations=[
        "2026-01-04",  # dte=3
        "2026-01-06",  # dte=5
        "2026-01-09",  # dte=8
        "2026-01-13",  # dte=12
        "2026-01-21",  # dte=20
    ])
    out = expirations_in_dte_window(client, "SPY", 7, 14, today=today)
    assert out == [
        ("2026-01-09", date(2026, 1, 9), 8),
        ("2026-01-13", date(2026, 1, 13), 12),
    ]


def test_expirations_window_matches_zero_returns_empty():
    today = date(2026, 1, 1)
    client = _mock_client(expirations=["2026-01-04", "2026-01-21"])
    out = expirations_in_dte_window(client, "SPY", 7, 14, today=today)
    assert out == []


def test_expirations_min_dte_boundary_inclusive():
    """exp on today+7 should be included when min_dte=7."""
    today = date(2026, 1, 1)
    client = _mock_client(expirations=["2026-01-08"])
    out = expirations_in_dte_window(client, "SPY", 7, 14, today=today)
    assert out == [("2026-01-08", date(2026, 1, 8), 7)]


def test_expirations_max_dte_boundary_inclusive():
    """exp on today+14 should be included when max_dte=14."""
    today = date(2026, 1, 1)
    client = _mock_client(expirations=["2026-01-15"])
    out = expirations_in_dte_window(client, "SPY", 7, 14, today=today)
    assert out == [("2026-01-15", date(2026, 1, 15), 14)]


def test_expirations_bad_date_string_skipped(caplog):
    today = date(2026, 1, 1)
    client = _mock_client(expirations=[
        "2026-01-09",  # valid, dte=8
        "garbage",     # invalid — skipped
        "2026-01-13",  # valid, dte=12
    ])
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    out = expirations_in_dte_window(client, "SPY", 7, 14, today=today)
    assert out == [
        ("2026-01-09", date(2026, 1, 9), 8),
        ("2026-01-13", date(2026, 1, 13), 12),
    ]
    assert any("invalid expiration" in r.getMessage() for r in caplog.records)


def test_expirations_get_expirations_raises_returns_empty(caplog):
    client = _mock_client(expirations=RuntimeError("ThetaData down"))
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    out = expirations_in_dte_window(client, "SPY", 7, 14)
    assert out == []
    assert any("get_expirations" in r.getMessage() for r in caplog.records)


# ─────────────────────────────────────────────────────────────────
# snapshot_underlying_price
# ─────────────────────────────────────────────────────────────────


def test_snapshot_underlying_returns_close():
    client = _mock_client(bars=_bars_df(500.25))
    assert snapshot_underlying_price(client, "SPY") == 500.25


def test_snapshot_underlying_get_stock_bars_raises(caplog):
    client = _mock_client(bars=RuntimeError("Alpaca down"))
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    assert snapshot_underlying_price(client, "SPY") is None
    assert any("snapshot_underlying_price" in r.getMessage() for r in caplog.records)


def test_snapshot_underlying_empty_dataframe(caplog):
    client = _mock_client(bars=pd.DataFrame())
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    assert snapshot_underlying_price(client, "SPY") is None
    assert any("empty" in r.getMessage() for r in caplog.records)


# ─────────────────────────────────────────────────────────────────
# build_option_contract
# ─────────────────────────────────────────────────────────────────


def test_build_contract_translates_call_uppercase_to_lowercase():
    raw = _raw_contract(500.0, right="CALL")
    oc = build_option_contract(
        "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
    )
    assert oc.right == "call"


def test_build_contract_translates_put_uppercase_to_lowercase():
    raw = _raw_contract(500.0, right="PUT")
    oc = build_option_contract(
        "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
    )
    assert oc.right == "put"


def test_build_contract_uses_passed_expiration_date():
    raw = _raw_contract(500.0)
    oc = build_option_contract(
        "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
    )
    assert oc.expiration == date(2026, 5, 15)


def test_build_contract_populates_delta_and_iv_from_greeks():
    raw = _raw_contract(500.0)
    g = _greeks(delta=0.62, iv=0.31)
    oc = build_option_contract(
        "SPY", raw, "2026-05-15", date(2026, 5, 15), g,
    )
    assert oc.delta == 0.62
    assert oc.iv == 0.31


def test_build_contract_missing_volume_defaults_zero():
    raw = _raw_contract(500.0)
    del raw["volume"]
    oc = build_option_contract(
        "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
    )
    assert oc.volume == 0


def test_build_contract_missing_open_interest_defaults_zero():
    raw = _raw_contract(500.0)
    del raw["open_interest"]
    oc = build_option_contract(
        "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
    )
    assert oc.open_interest == 0


def test_build_contract_missing_bid_raises():
    raw = _raw_contract(500.0)
    del raw["bid"]
    with pytest.raises(KeyError):
        build_option_contract(
            "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
        )


def test_build_contract_missing_ask_raises():
    raw = _raw_contract(500.0)
    del raw["ask"]
    with pytest.raises(KeyError):
        build_option_contract(
            "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
        )


def test_build_contract_missing_mid_raises():
    raw = _raw_contract(500.0)
    del raw["mid"]
    with pytest.raises(KeyError):
        build_option_contract(
            "SPY", raw, "2026-05-15", date(2026, 5, 15), _greeks(),
        )


# ─────────────────────────────────────────────────────────────────
# build_option_chain
# ─────────────────────────────────────────────────────────────────


def test_build_chain_happy_path_filters_to_in_band_calls():
    """5 raw + 1 wrong-side: 3 in-band CALL with bid/ask>0 → greeks called 3×."""
    underlying = 500.0
    raw_chain = [
        _raw_contract(480.0, "CALL", bid=20.0, ask=20.5),    # in band, call
        _raw_contract(500.0, "CALL", bid=10.0, ask=10.2),    # in band, call
        _raw_contract(510.0, "CALL", bid=5.0, ask=5.2),      # in band, call
        _raw_contract(490.0, "PUT", bid=2.0, ask=2.2),       # wrong right
        _raw_contract(530.0, "CALL", bid=2.0, ask=2.2),      # out of band
        _raw_contract(485.0, "CALL", bid=0.0, ask=0.1),      # zero bid
    ]
    client = _mock_client(chain=raw_chain, greeks=_greeks())
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=underlying,
    )
    assert chain is not None
    assert len(chain.contracts) == 3
    assert client.get_greeks.call_count == 3
    strikes = sorted(c.strike for c in chain.contracts)
    assert strikes == [480.0, 500.0, 510.0]
    # Right was lowercased
    assert all(c.right == "call" for c in chain.contracts)


def test_build_chain_underlying_price_provided_skips_fetch():
    client = _mock_client(chain=[], greeks=_greeks())
    build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=500.0,
    )
    client.get_stock_bars.assert_not_called()


def test_build_chain_underlying_price_none_triggers_snapshot():
    client = _mock_client(chain=[], bars=_bars_df(500.0))
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call",
    )
    client.get_stock_bars.assert_called_once_with("SPY", "1Min", 1)
    assert chain is not None
    assert chain.underlying_price == 500.0


def test_build_chain_no_underlying_returns_none(caplog):
    client = _mock_client(bars=pd.DataFrame())  # empty
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call",
    )
    assert chain is None
    assert any("no underlying price" in r.getMessage() for r in caplog.records)


def test_build_chain_get_options_chain_raises_returns_none(caplog):
    client = _mock_client(chain=RuntimeError("ThetaData down"))
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=500.0,
    )
    assert chain is None
    assert any("get_options_chain" in r.getMessage() for r in caplog.records)


def test_build_chain_empty_raw_chain_returns_empty_contracts():
    client = _mock_client(chain=[])
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=500.0,
    )
    assert chain is not None
    assert chain.contracts == []
    assert chain.underlying_price == 500.0


def test_build_chain_right_filter_excludes_wrong_side_pre_greeks():
    """PUT contracts in the chain must NOT trigger greeks calls when
    right_filter='call'."""
    underlying = 500.0
    raw_chain = [
        _raw_contract(495.0, "PUT", bid=2.0, ask=2.2),
        _raw_contract(505.0, "PUT", bid=2.0, ask=2.2),
    ]
    client = _mock_client(chain=raw_chain, greeks=_greeks())
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=underlying,
    )
    assert chain is not None
    assert chain.contracts == []
    assert client.get_greeks.call_count == 0


def test_build_chain_strike_outside_band_excluded_pre_greeks():
    """Strikes outside ±5% must not trigger greeks calls. Underlying 500,
    band [475, 525]. 470 and 530 are out; 500 is in."""
    underlying = 500.0
    raw_chain = [
        _raw_contract(470.0, "CALL", bid=30.0, ask=30.5),    # below band
        _raw_contract(500.0, "CALL", bid=10.0, ask=10.2),    # in band
        _raw_contract(530.0, "CALL", bid=2.0, ask=2.2),      # above band
    ]
    client = _mock_client(chain=raw_chain, greeks=_greeks())
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=underlying,
    )
    assert chain is not None
    assert len(chain.contracts) == 1
    assert chain.contracts[0].strike == 500.0
    assert client.get_greeks.call_count == 1


def test_build_chain_zero_bid_excluded_pre_greeks():
    underlying = 500.0
    raw_chain = [
        _raw_contract(500.0, "CALL", bid=0.0, ask=0.1),   # zero bid
        _raw_contract(505.0, "CALL", bid=8.0, ask=8.2),   # ok
    ]
    client = _mock_client(chain=raw_chain, greeks=_greeks())
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=underlying,
    )
    assert chain is not None
    assert len(chain.contracts) == 1
    assert chain.contracts[0].strike == 505.0
    assert client.get_greeks.call_count == 1


def test_build_chain_one_greeks_failure_skips_that_contract(caplog):
    """3 candidates; greeks fails on the second. Chain returns the other 2."""
    underlying = 500.0
    raw_chain = [
        _raw_contract(495.0, "CALL", bid=8.0, ask=8.2),
        _raw_contract(500.0, "CALL", bid=10.0, ask=10.2),
        _raw_contract(505.0, "CALL", bid=12.0, ask=12.2),
    ]

    def _greeks_side_effect(symbol, exp, strike, right):
        if strike == 500.0:
            raise RuntimeError("ThetaData hiccup")
        return _greeks()

    client = _mock_client(chain=raw_chain)
    client.get_greeks.side_effect = _greeks_side_effect
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")

    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=underlying,
    )
    assert chain is not None
    strikes = sorted(c.strike for c in chain.contracts)
    assert strikes == [495.0, 505.0]
    assert any("get_greeks" in r.getMessage() for r in caplog.records)


def test_build_chain_all_greeks_fail_returns_empty_not_none():
    """Every greeks call raises. Chain still returned with empty contracts —
    degraded, not failed."""
    underlying = 500.0
    raw_chain = [
        _raw_contract(495.0, "CALL", bid=8.0, ask=8.2),
        _raw_contract(500.0, "CALL", bid=10.0, ask=10.2),
    ]
    client = _mock_client(
        chain=raw_chain,
        greeks=RuntimeError("ThetaData fully down"),
    )
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=underlying,
    )
    assert chain is not None
    assert chain.contracts == []
    assert chain.underlying_price == underlying


def test_build_chain_snapshot_time_is_utc_aware():
    client = _mock_client(chain=[])
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=500.0,
    )
    assert chain is not None
    assert chain.snapshot_time.tzinfo is not None
    # Compare offset to UTC's offset (timezone.utc)
    assert chain.snapshot_time.utcoffset() == timezone.utc.utcoffset(
        datetime.now(timezone.utc)
    )


# ─────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────


def test_ntm_band_pct_is_five_percent():
    """Documented ±5% band — guard against accidental tweaks."""
    assert NTM_BAND_PCT == 0.05


# ─────────────────────────────────────────────────────────────────
# Type assertions
# ─────────────────────────────────────────────────────────────────


def test_build_chain_returns_option_chain_type():
    client = _mock_client(chain=[])
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=500.0,
    )
    assert isinstance(chain, OptionChain)


def test_build_chain_contracts_are_option_contract_type():
    underlying = 500.0
    raw_chain = [_raw_contract(500.0, "CALL", bid=10.0, ask=10.2)]
    client = _mock_client(chain=raw_chain, greeks=_greeks())
    chain = build_option_chain(
        client, "SPY", "2026-05-15", date(2026, 5, 15),
        right_filter="call", underlying_price=underlying,
    )
    assert chain is not None
    assert all(isinstance(c, OptionContract) for c in chain.contracts)


# ─────────────────────────────────────────────────────────────────
# prefer_symbol_specific_expirations
# ─────────────────────────────────────────────────────────────────
#
# Date mapping reference (weekday() values, Mon=0..Sun=6):
#   2026-05-15 Fri (4)     2026-05-18 Mon (0)     2026-05-20 Wed (2)
#   2026-05-22 Fri (4)     2026-05-29 Fri (4)     2026-06-05 Fri (4)


def _cand(exp_date: date, dte: int) -> tuple[str, date, int]:
    return (exp_date.isoformat(), exp_date, dte)


def test_prefer_spy_filters_to_fridays_only():
    candidates = [
        _cand(date(2026, 5, 15), 7),   # Fri
        _cand(date(2026, 5, 18), 10),  # Mon
        _cand(date(2026, 5, 20), 12),  # Wed
        _cand(date(2026, 5, 22), 14),  # Fri
    ]
    out = prefer_symbol_specific_expirations("SPY", candidates)
    assert out == [
        _cand(date(2026, 5, 15), 7),
        _cand(date(2026, 5, 22), 14),
    ]


def test_prefer_spy_all_fridays_returns_all():
    candidates = [
        _cand(date(2026, 5, 15), 7),
        _cand(date(2026, 5, 22), 14),
        _cand(date(2026, 5, 29), 21),
    ]
    out = prefer_symbol_specific_expirations("SPY", candidates)
    assert out == candidates


def test_prefer_spy_no_fridays_returns_empty_with_warning(caplog):
    candidates = [
        _cand(date(2026, 5, 18), 10),  # Mon
        _cand(date(2026, 5, 20), 12),  # Wed
    ]
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    out = prefer_symbol_specific_expirations("SPY", candidates)
    assert out == []
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("emptied" in r.getMessage() for r in warns)


def test_prefer_spy_partial_filter_logs_info(caplog):
    """SPY filter that reduces (but doesn't empty) the list logs info."""
    candidates = [
        _cand(date(2026, 5, 15), 7),   # Fri
        _cand(date(2026, 5, 18), 10),  # Mon — filtered
    ]
    caplog.set_level(logging.INFO, logger="options-bot.data.chain_adapter")
    prefer_symbol_specific_expirations("SPY", candidates)
    infos = [r for r in caplog.records if r.levelname == "INFO"]
    assert any("2 -> 1" in r.getMessage() for r in infos), (
        f"expected info-level reduction message, got: "
        f"{[r.getMessage() for r in infos]}"
    )


def test_prefer_spy_empty_input_no_warning(caplog):
    """Empty input -> empty output, no warning (no information was lost)."""
    caplog.set_level(logging.WARNING, logger="options-bot.data.chain_adapter")
    out = prefer_symbol_specific_expirations("SPY", [])
    assert out == []
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warns == []


def test_prefer_non_spy_symbol_returns_unchanged():
    candidates = [
        _cand(date(2026, 5, 15), 7),   # Fri
        _cand(date(2026, 5, 18), 10),  # Mon
        _cand(date(2026, 5, 20), 12),  # Wed
        _cand(date(2026, 5, 22), 14),  # Fri
    ]
    out = prefer_symbol_specific_expirations("TSLA", candidates)
    assert out == candidates


def test_prefer_non_spy_returns_new_list_object():
    """Defensive copy: TSLA result must not be the same list as input."""
    candidates = [_cand(date(2026, 5, 18), 10)]
    out = prefer_symbol_specific_expirations("TSLA", candidates)
    assert out == candidates
    assert out is not candidates


def test_prefer_spy_returns_new_list_object():
    """SPY result must also be a new list (defensive copy contract)."""
    candidates = [_cand(date(2026, 5, 15), 7)]  # all Fridays
    out = prefer_symbol_specific_expirations("SPY", candidates)
    assert out == candidates
    assert out is not candidates


def test_prefer_spy_preserves_sort_order():
    """When filtering, surviving Fridays appear in input order (DTE asc)."""
    candidates = [
        _cand(date(2026, 5, 15), 7),    # Fri
        _cand(date(2026, 5, 18), 10),   # Mon — drop
        _cand(date(2026, 5, 22), 14),   # Fri
        _cand(date(2026, 5, 29), 21),   # Fri
        _cand(date(2026, 6, 5), 28),    # Fri
    ]
    out = prefer_symbol_specific_expirations("SPY", candidates)
    assert [c[2] for c in out] == [7, 14, 21, 28]
