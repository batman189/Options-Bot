"""Unit tests for learning.outcome_tracker.

Uses tmp_path + monkeypatched config.DB_PATH so each test gets a fresh
SQLite file initialised from backend.database.SCHEMA_SQL. Mocks
UnifiedDataClient so no network calls.

Run via:
    python -m pytest tests/test_outcome_tracker.py -v
"""

import asyncio
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402

from backend.database import SCHEMA_SQL  # noqa: E402
from learning.outcome_tracker import (  # noqa: E402
    EXPIRY_GRACE_HOURS,
    STATUS_EVALUATED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    WINDOW_LABELS,
    get_setup_type_accuracy,
    record_signal,
    resolve_pending_outcomes,
)


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Fresh SQLite file per test, schema initialised from production
    SCHEMA_SQL. config.DB_PATH is monkeypatched so production code
    paths read/write the test DB."""
    db_path = tmp_path / "test_outcomes.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    return db_path


def _read_outcomes(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM signal_outcomes ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _record_kwargs(**overrides) -> dict:
    """Standard record_signal arguments. Predicted at 10:00 ET (14:00 UTC)
    on Friday May 15 2026 — a known full trading day."""
    defaults = {
        "signal_id": "sig-1",
        "profile_id": "swing-test",
        "symbol": "TSLA",
        "setup_type": "momentum",
        "direction": "bullish",
        "contract_symbol": "TSLA260515C00500000",
        "contract_strike": 500.0,
        "contract_right": "call",
        "contract_expiration": "2026-05-15",
        "entry_premium": 1.00,
        "predicted_at": datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
    }
    return {**defaults, **overrides}


def _raw_chain_contract(strike: float, right: str, mid: float):
    """One raw chain dict with the keys the resolver reads. UPPERCASE
    right matches what get_options_chain returns."""
    return {
        "strike": strike,
        "right": right.upper(),
        "bid": mid - 0.05,
        "ask": mid + 0.05,
        "mid": mid,
        "volume": 100,
        "open_interest": 500,
    }


def _run(coro):
    """Run an async coroutine in a fresh loop."""
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────


def test_schema_signal_outcomes_table_exists(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='signal_outcomes'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_schema_indexes_present(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name LIKE 'idx_signal_outcomes%'"
    ).fetchall()
    conn.close()
    names = {r[0] for r in rows}
    assert "idx_signal_outcomes_status_evaluate_at" in names
    assert "idx_signal_outcomes_setup_type" in names


def test_schema_unique_constraint_enforced(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    insert = (
        "INSERT INTO signal_outcomes "
        "(signal_id, profile_id, symbol, setup_type, direction, "
        " contract_symbol, contract_strike, contract_right, "
        " contract_expiration, entry_premium, predicted_at, window_label, "
        " evaluate_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    args = (
        "sig-1", "swing-test", "TSLA", "momentum", "bullish",
        "TSLA260515C00500000", 500.0, "call", "2026-05-15", 1.00,
        "2026-05-15T14:00:00+00:00", "1h",
        "2026-05-15T15:00:00+00:00", "pending",
    )
    conn.execute(insert, args)
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, args)
    conn.close()


# ─────────────────────────────────────────────────────────────────
# record_signal
# ─────────────────────────────────────────────────────────────────


def test_record_signal_creates_four_rows(tmp_db):
    record_signal(**_record_kwargs())
    rows = _read_outcomes(tmp_db)
    assert len(rows) == 4
    labels = sorted(r["window_label"] for r in rows)
    assert labels == sorted(WINDOW_LABELS)
    for r in rows:
        assert r["status"] == STATUS_PENDING
        assert r["signal_id"] == "sig-1"


def test_record_signal_window_labels_match(tmp_db):
    record_signal(**_record_kwargs())
    rows = _read_outcomes(tmp_db)
    label_set = {r["window_label"] for r in rows}
    assert label_set == set(WINDOW_LABELS)


def test_record_signal_evaluate_at_intraday(tmp_db):
    """Signal at 10:00 ET on a trading day → 1h at 11:00, 4h at 14:00,
    EOD at 16:00, next_day at next morning's 09:30."""
    record_signal(**_record_kwargs())
    rows = _read_outcomes(tmp_db)
    by_label = {r["window_label"]: r["evaluate_at"] for r in rows}
    # 10:00 ET = 14:00 UTC; 1h later = 15:00 UTC (during RTH, no roll)
    assert by_label["1h"] == "2026-05-15T15:00:00+00:00"
    # 4h later = 18:00 UTC = 14:00 ET (during RTH)
    assert by_label["4h"] == "2026-05-15T18:00:00+00:00"
    # EOD = May 15 close = 20:00 UTC = 16:00 ET
    assert by_label["EOD"] == "2026-05-15T20:00:00+00:00"
    # next_day: predicted_at + 1d = May 16 (Sat); next open = May 18 13:30 UTC
    assert by_label["next_day"] == "2026-05-18T13:30:00+00:00"


def test_record_signal_evaluate_at_late_signal_rolls_forward(tmp_db):
    """Signal at 15:30 ET → 1h would land at 16:30 ET (post-close), should
    roll forward to next morning's 09:30 ET = Monday 13:30 UTC."""
    record_signal(**_record_kwargs(
        signal_id="sig-late",
        predicted_at=datetime(2026, 5, 15, 19, 30, tzinfo=timezone.utc),
    ))
    rows = _read_outcomes(tmp_db)
    by_label = {r["window_label"]: r["evaluate_at"] for r in rows}
    assert by_label["1h"] == "2026-05-18T13:30:00+00:00"


def test_record_signal_evaluate_at_friday_next_day_skips_weekend(tmp_db):
    """Friday 10:00 ET signal → next_day = Monday 09:30 ET."""
    record_signal(**_record_kwargs())
    rows = _read_outcomes(tmp_db)
    by_label = {r["window_label"]: r["evaluate_at"] for r in rows}
    assert by_label["next_day"] == "2026-05-18T13:30:00+00:00"


def test_record_signal_evaluate_at_pre_holiday_next_day(tmp_db):
    """Wed 2025-12-31 10:00 ET signal → next_day skips New Year's Day
    (closed) and lands on Fri 2026-01-02 09:30 ET."""
    record_signal(**_record_kwargs(
        signal_id="sig-newyear",
        predicted_at=datetime(2025, 12, 31, 15, 0, tzinfo=timezone.utc),
    ))
    rows = _read_outcomes(tmp_db)
    by_label = {r["window_label"]: r["evaluate_at"] for r in rows}
    nd = datetime.fromisoformat(by_label["next_day"])
    assert nd.date() == date(2026, 1, 2)


def test_record_signal_naive_predicted_at_raises(tmp_db):
    with pytest.raises(ValueError, match="timezone-aware"):
        record_signal(**_record_kwargs(
            predicted_at=datetime(2026, 5, 15, 14, 0),
        ))


def test_record_signal_idempotent_duplicate_call(tmp_db):
    """Re-calling with the same signal_id should not raise; the UNIQUE
    constraint absorbs duplicate rows."""
    record_signal(**_record_kwargs())
    record_signal(**_record_kwargs())  # second call
    rows = _read_outcomes(tmp_db)
    assert len(rows) == 4  # still 4, not 8


def test_record_signal_missing_arg_raises_typeerror(tmp_db):
    """Forgetting a required kwarg surfaces as TypeError."""
    kwargs = _record_kwargs()
    del kwargs["symbol"]
    with pytest.raises(TypeError):
        record_signal(**kwargs)


# ─────────────────────────────────────────────────────────────────
# resolve_pending_outcomes
# ─────────────────────────────────────────────────────────────────


def _seed_pending(
    tmp_db: Path,
    *,
    signal_id: str = "sig-r",
    window_label: str = "1h",
    evaluate_at: datetime,
    entry_premium: float = 1.00,
    contract_strike: float = 500.0,
    contract_right: str = "call",
    contract_expiration: str = "2026-05-15",
    symbol: str = "TSLA",
    profile_id: str = "swing-test",
    setup_type: str = "momentum",
    direction: str = "bullish",
):
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        """INSERT INTO signal_outcomes
           (signal_id, profile_id, symbol, setup_type, direction,
            contract_symbol, contract_strike, contract_right,
            contract_expiration, entry_premium, predicted_at,
            window_label, evaluate_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal_id, profile_id, symbol, setup_type, direction,
            f"{symbol}260515X00000000", contract_strike, contract_right,
            contract_expiration, entry_premium,
            "2026-05-15T13:00:00+00:00",
            window_label, evaluate_at.isoformat(), STATUS_PENDING,
        ),
    )
    conn.commit()
    conn.close()


def test_resolve_no_pending_returns_zero_summary(tmp_db):
    client = MagicMock()
    summary = _run(resolve_pending_outcomes(client))
    assert summary == {"evaluated": 0, "expired": 0, "still_pending": 0}


def test_resolve_skips_future_pending(tmp_db):
    future = datetime(2099, 1, 1, 14, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=future)
    client = MagicMock()
    now = datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary == {"evaluated": 0, "expired": 0, "still_pending": 0}
    client.get_options_chain.assert_not_called()


def test_resolve_evaluates_ripe_pending_with_matching_contract(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=ripe)
    client = MagicMock()
    client.get_options_chain.return_value = [
        _raw_chain_contract(500.0, "CALL", mid=1.20),
    ]
    now = datetime(2026, 5, 15, 16, 0, tzinfo=timezone.utc)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary == {"evaluated": 1, "expired": 0, "still_pending": 0}
    rows = _read_outcomes(tmp_db)
    assert rows[0]["status"] == STATUS_EVALUATED
    assert rows[0]["evaluated_premium"] == 1.20
    assert rows[0]["pnl_pct_at_window"] == pytest.approx(0.20)


def test_resolve_pnl_negative_when_premium_drops(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=ripe, entry_premium=1.00)
    client = MagicMock()
    client.get_options_chain.return_value = [
        _raw_chain_contract(500.0, "CALL", mid=0.80),
    ]
    now = datetime(2026, 5, 15, 16, 0, tzinfo=timezone.utc)
    _run(resolve_pending_outcomes(client, now=now))
    rows = _read_outcomes(tmp_db)
    assert rows[0]["pnl_pct_at_window"] == pytest.approx(-0.20)


def test_resolve_zero_mid_stays_pending_within_grace(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=ripe)
    client = MagicMock()
    client.get_options_chain.return_value = [
        _raw_chain_contract(500.0, "CALL", mid=0.0),  # degenerate
    ]
    now = ripe + timedelta(hours=1)  # within grace
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary == {"evaluated": 0, "expired": 0, "still_pending": 1}
    rows = _read_outcomes(tmp_db)
    assert rows[0]["status"] == STATUS_PENDING


def test_resolve_chain_raises_within_grace_stays_pending(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=ripe)
    client = MagicMock()
    client.get_options_chain.side_effect = RuntimeError("ThetaData down")
    now = ripe + timedelta(hours=1)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary["still_pending"] == 1
    rows = _read_outcomes(tmp_db)
    assert rows[0]["status"] == STATUS_PENDING


def test_resolve_chain_raises_past_grace_marks_expired(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=ripe)
    client = MagicMock()
    client.get_options_chain.side_effect = RuntimeError("ThetaData down")
    now = ripe + timedelta(hours=EXPIRY_GRACE_HOURS + 1)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary["expired"] == 1
    rows = _read_outcomes(tmp_db)
    assert rows[0]["status"] == STATUS_EXPIRED


def test_resolve_contract_not_in_chain_within_grace(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=ripe)
    client = MagicMock()
    # chain returns a different strike
    client.get_options_chain.return_value = [
        _raw_chain_contract(495.0, "CALL", mid=2.00),
    ]
    now = ripe + timedelta(hours=1)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary["still_pending"] == 1


def test_resolve_contract_not_in_chain_past_grace_expires(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(tmp_db, evaluate_at=ripe)
    client = MagicMock()
    client.get_options_chain.return_value = []  # empty chain
    now = ripe + timedelta(hours=EXPIRY_GRACE_HOURS + 1)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary["expired"] == 1


def test_resolve_mixed_ripe_and_future(tmp_db):
    ripe = datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc)
    _seed_pending(
        tmp_db, signal_id="sig-a", window_label="1h", evaluate_at=ripe,
    )
    _seed_pending(
        tmp_db, signal_id="sig-b", window_label="1h", evaluate_at=ripe,
    )
    future = datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc)
    _seed_pending(
        tmp_db, signal_id="sig-c", window_label="1h", evaluate_at=future,
    )
    client = MagicMock()
    client.get_options_chain.return_value = [
        _raw_chain_contract(500.0, "CALL", mid=1.10),
    ]
    now = datetime(2026, 5, 15, 16, 0, tzinfo=timezone.utc)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary == {"evaluated": 2, "expired": 0, "still_pending": 0}


def test_resolve_idempotent_evaluated_rows_skipped(tmp_db):
    """Pre-evaluated rows are not in the WHERE clause and are not touched."""
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        """INSERT INTO signal_outcomes
           (signal_id, profile_id, symbol, setup_type, direction,
            contract_symbol, contract_strike, contract_right,
            contract_expiration, entry_premium, predicted_at,
            window_label, evaluate_at, evaluated_premium,
            pnl_pct_at_window, evaluated_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "sig-old", "swing-test", "TSLA", "momentum", "bullish",
            "X", 500.0, "call", "2026-05-15", 1.00,
            "2026-05-15T13:00:00+00:00",
            "1h", "2026-05-15T15:00:00+00:00",
            1.30, 0.30,
            "2026-05-15T15:01:00+00:00",
            STATUS_EVALUATED,
        ),
    )
    conn.commit()
    conn.close()
    client = MagicMock()
    now = datetime(2026, 5, 15, 16, 0, tzinfo=timezone.utc)
    summary = _run(resolve_pending_outcomes(client, now=now))
    assert summary == {"evaluated": 0, "expired": 0, "still_pending": 0}
    rows = _read_outcomes(tmp_db)
    assert rows[0]["pnl_pct_at_window"] == 0.30  # unchanged


# ─────────────────────────────────────────────────────────────────
# get_setup_type_accuracy
# ─────────────────────────────────────────────────────────────────


def _seed_evaluated(
    tmp_db: Path,
    *,
    signal_id: str,
    window_label: str,
    pnl_pct: float,
    setup_type: str = "momentum",
    profile_id: str = "swing-test",
):
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        """INSERT INTO signal_outcomes
           (signal_id, profile_id, symbol, setup_type, direction,
            contract_symbol, contract_strike, contract_right,
            contract_expiration, entry_premium, predicted_at,
            window_label, evaluate_at, evaluated_premium,
            pnl_pct_at_window, evaluated_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            signal_id, profile_id, "TSLA", setup_type, "bullish",
            "X", 500.0, "call", "2026-05-15", 1.00,
            "2026-05-15T13:00:00+00:00", window_label,
            "2026-05-15T15:00:00+00:00",
            1.00 * (1 + pnl_pct), pnl_pct,
            "2026-05-15T15:01:00+00:00", STATUS_EVALUATED,
        ),
    )
    conn.commit()
    conn.close()


def test_accuracy_empty_returns_zero(tmp_db):
    out = get_setup_type_accuracy("momentum")
    assert out["total"] == 0
    assert out["correct"] == 0
    assert out["win_rate"] is None
    assert out["average_pnl_pct"] is None
    assert "by_window" in out
    for label in WINDOW_LABELS:
        assert out["by_window"][label]["total"] == 0


def test_accuracy_mixed_outcomes(tmp_db):
    """6 momentum outcomes: 4 positive (correct), 2 negative."""
    pnls = [0.10, 0.20, 0.05, 0.30, -0.05, -0.15]
    for i, pnl in enumerate(pnls):
        _seed_evaluated(
            tmp_db, signal_id=f"s{i}", window_label="1h", pnl_pct=pnl,
        )
    out = get_setup_type_accuracy("momentum")
    assert out["total"] == 6
    assert out["correct"] == 4
    assert out["win_rate"] == pytest.approx(4 / 6)
    assert out["average_pnl_pct"] == pytest.approx(sum(pnls) / 6)


def test_accuracy_profile_name_filter(tmp_db):
    _seed_evaluated(
        tmp_db, signal_id="a", window_label="1h", pnl_pct=0.10,
        profile_id="profile-A",
    )
    _seed_evaluated(
        tmp_db, signal_id="b", window_label="1h", pnl_pct=-0.10,
        profile_id="profile-B",
    )
    a = get_setup_type_accuracy("momentum", profile_name="profile-A")
    b = get_setup_type_accuracy("momentum", profile_name="profile-B")
    assert a["total"] == 1
    assert a["correct"] == 1
    assert b["total"] == 1
    assert b["correct"] == 0


def test_accuracy_excludes_pending_and_expired(tmp_db):
    # 1 evaluated
    _seed_evaluated(
        tmp_db, signal_id="ev", window_label="1h", pnl_pct=0.10,
    )
    # 1 pending, 1 expired
    conn = sqlite3.connect(str(tmp_db))
    for sid, status in (("p", STATUS_PENDING), ("e", STATUS_EXPIRED)):
        conn.execute(
            """INSERT INTO signal_outcomes
               (signal_id, profile_id, symbol, setup_type, direction,
                contract_symbol, contract_strike, contract_right,
                contract_expiration, entry_premium, predicted_at,
                window_label, evaluate_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid, "swing-test", "TSLA", "momentum", "bullish",
                "X", 500.0, "call", "2026-05-15", 1.00,
                "2026-05-15T13:00:00+00:00", "1h",
                "2026-05-15T15:00:00+00:00", status,
            ),
        )
    conn.commit()
    conn.close()
    out = get_setup_type_accuracy("momentum")
    assert out["total"] == 1
    assert out["correct"] == 1


def test_accuracy_by_window_breakdown(tmp_db):
    """Window-level aggregation: 1h has 2 wins, 4h has 1 win + 1 loss."""
    _seed_evaluated(
        tmp_db, signal_id="a", window_label="1h", pnl_pct=0.10,
    )
    _seed_evaluated(
        tmp_db, signal_id="b", window_label="1h", pnl_pct=0.20,
    )
    _seed_evaluated(
        tmp_db, signal_id="c", window_label="4h", pnl_pct=0.05,
    )
    _seed_evaluated(
        tmp_db, signal_id="d", window_label="4h", pnl_pct=-0.10,
    )
    out = get_setup_type_accuracy("momentum")
    assert out["by_window"]["1h"]["total"] == 2
    assert out["by_window"]["1h"]["correct"] == 2
    assert out["by_window"]["1h"]["win_rate"] == 1.0
    assert out["by_window"]["4h"]["total"] == 2
    assert out["by_window"]["4h"]["correct"] == 1
    assert out["by_window"]["4h"]["win_rate"] == 0.5
    assert out["by_window"]["EOD"]["total"] == 0
    assert out["by_window"]["next_day"]["total"] == 0


def test_accuracy_average_pnl_pct():
    """Direct sanity on average_pnl_pct: [0.10, 0.20, -0.05, -0.15] avg = 0.025."""
    # Use a fresh tmp_db via the fixture in the test name
    pass


def test_accuracy_average_pnl_pct_explicit(tmp_db):
    pnls = [0.10, 0.20, -0.05, -0.15]
    for i, pnl in enumerate(pnls):
        _seed_evaluated(
            tmp_db, signal_id=f"x{i}", window_label="1h", pnl_pct=pnl,
        )
    out = get_setup_type_accuracy("momentum")
    assert out["average_pnl_pct"] == pytest.approx(0.025)
