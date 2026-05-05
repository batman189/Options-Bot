"""Unit tests for backend.outcome_resolver — the FastAPI lifespan
periodic task that drives outcome_tracker.resolve_pending_outcomes.

C5c (final Phase 1a wire-in). Tests assert on start/stop semantics,
loop body call patterns, and lifespan integration. Real network
calls and long sleeps are avoided — UnifiedDataClient is patched at
the module level, asyncio.run is patched to capture the resolver
invocation, and the loop is short-circuited via the
_resolver_running flag rather than waiting the full interval.

Run via:
    python -m pytest tests/test_outcome_resolver.py -v
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import outcome_resolver  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state before and after each test so tests
    don't leak state into one another. Also stops any thread that
    may have been started by a flaky prior test."""
    outcome_resolver._resolver_running = False
    outcome_resolver._resolver_thread = None
    outcome_resolver._resolver_client = None
    yield
    outcome_resolver._resolver_running = False
    if outcome_resolver._resolver_thread is not None:
        # Best-effort join so threads from individual tests don't
        # outlive the test session.
        outcome_resolver._resolver_thread.join(timeout=2)
    outcome_resolver._resolver_thread = None
    outcome_resolver._resolver_client = None


def _patch_client_class(succeed: bool = True):
    """Return a context-manager-style patch on the UnifiedDataClient
    class as referenced inside outcome_resolver. Health check raises
    when succeed=False."""
    if succeed:
        client = MagicMock()
        client.health_check.return_value = None
        return patch.object(
            outcome_resolver, "UnifiedDataClient",
            return_value=client,
        )
    client = MagicMock()
    client.health_check.side_effect = RuntimeError("unhealthy")
    return patch.object(
        outcome_resolver, "UnifiedDataClient",
        return_value=client,
    )


# ═════════════════════════════════════════════════════════════════
# start_outcome_resolver_loop
# ═════════════════════════════════════════════════════════════════


def test_start_with_healthy_client_sets_running_flag():
    """start returns True, _resolver_running is True, _resolver_client
    is set, _resolver_thread is set. Does NOT actually run a tick:
    we patch _resolver_loop with a no-op so the thread exits
    immediately."""
    with _patch_client_class(succeed=True), \
         patch.object(outcome_resolver, "_resolver_loop", lambda: None):
        result = outcome_resolver.start_outcome_resolver_loop()

    assert result is True
    assert outcome_resolver._resolver_running is True
    assert outcome_resolver._resolver_client is not None
    assert outcome_resolver._resolver_thread is not None


def test_start_idempotent_returns_true_without_recreating_thread():
    with _patch_client_class(succeed=True), \
         patch.object(outcome_resolver, "_resolver_loop", lambda: None):
        first_result = outcome_resolver.start_outcome_resolver_loop()
        first_thread = outcome_resolver._resolver_thread
        second_result = outcome_resolver.start_outcome_resolver_loop()
        second_thread = outcome_resolver._resolver_thread

    assert first_result is True
    assert second_result is True
    assert first_thread is second_thread


def test_start_with_unhealthy_client_spawns_thread_in_waiting_state():
    """FIX-2: when the initial health check fails (e.g. pre-market
    IV=0 raises DataNotReadyError), the thread spawns anyway in a
    waiting state. _resolver_client stays None until a future tick's
    reconnect succeeds. Pre-FIX-2 behavior was return False + no
    thread spawn; that lost outcome rows for the entire lifespan
    when operators started the bot pre-market."""
    with _patch_client_class(succeed=False), \
         patch.object(outcome_resolver, "_resolver_loop", lambda: None):
        result = outcome_resolver.start_outcome_resolver_loop()

    assert result is True
    assert outcome_resolver._resolver_running is True
    assert outcome_resolver._resolver_thread is not None
    assert outcome_resolver._resolver_client is None


def test_start_with_unhealthy_client_logs_info_waiting_state(caplog):
    """FIX-2: log level changed from WARNING to INFO on initial
    health-check failure — pre-market is expected operator state, not
    an error condition. The log message must mention 'waiting state'
    so operators reading the log can distinguish 'spawned in waiting'
    from 'spawned active'."""
    import logging
    caplog.set_level(logging.INFO, logger="backend.outcome_resolver")
    with _patch_client_class(succeed=False), \
         patch.object(outcome_resolver, "_resolver_loop", lambda: None):
        outcome_resolver.start_outcome_resolver_loop()

    assert any(
        "waiting state" in r.message
        and r.levelno == logging.INFO
        for r in caplog.records
    )


def test_start_logs_info_with_interval():
    import logging
    with _patch_client_class(succeed=True), \
         patch.object(outcome_resolver, "_resolver_loop", lambda: None):
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 300,
        ), patch.object(outcome_resolver.logger, "info") as info_log:
            outcome_resolver.start_outcome_resolver_loop()

    # Confirm an info log mentioning interval=300s was emitted.
    info_messages = [
        call.args[0] % call.args[1:] if len(call.args) > 1 else call.args[0]
        for call in info_log.call_args_list
    ]
    assert any("300" in m and "interval" in m for m in info_messages)


# ═════════════════════════════════════════════════════════════════
# stop_outcome_resolver_loop
# ═════════════════════════════════════════════════════════════════


def test_stop_after_start_clears_running_flag():
    with _patch_client_class(succeed=True), \
         patch.object(outcome_resolver, "_resolver_loop", lambda: None):
        outcome_resolver.start_outcome_resolver_loop()
        assert outcome_resolver._resolver_running is True

        outcome_resolver.stop_outcome_resolver_loop()

    assert outcome_resolver._resolver_running is False


def test_stop_idempotent_when_already_stopped():
    """Calling stop twice is a debug-logged no-op the second time."""
    with _patch_client_class(succeed=True), \
         patch.object(outcome_resolver, "_resolver_loop", lambda: None):
        outcome_resolver.start_outcome_resolver_loop()
    outcome_resolver.stop_outcome_resolver_loop()
    # Second call — no error, still stopped.
    outcome_resolver.stop_outcome_resolver_loop()
    assert outcome_resolver._resolver_running is False


def test_stop_without_prior_start_is_noop():
    """No exception, debug log only."""
    outcome_resolver.stop_outcome_resolver_loop()
    assert outcome_resolver._resolver_running is False


# ═════════════════════════════════════════════════════════════════
# _resolver_loop body
# ═════════════════════════════════════════════════════════════════


def test_loop_calls_resolve_pending_outcomes_per_tick():
    """A single tick invokes asyncio.run wrapping
    resolve_pending_outcomes(_resolver_client). We arm the loop with
    interval=1, mock asyncio.run to return a fake summary, and stop
    after the first tick by flipping _resolver_running."""
    fake_summary = {"evaluated": 1, "expired": 0, "still_pending": 2}
    asyncio_run_calls = []

    def fake_asyncio_run(coro):
        # Cancel the coroutine to suppress the "never awaited" warning.
        coro.close()
        asyncio_run_calls.append("called")
        # Stop the loop after the first tick.
        outcome_resolver._resolver_running = False
        return fake_summary

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = MagicMock()
    with patch.object(outcome_resolver, "asyncio") as fake_asyncio:
        fake_asyncio.run = fake_asyncio_run
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 1,
        ):
            outcome_resolver._resolver_loop()

    assert asyncio_run_calls == ["called"]


def test_loop_logs_tick_result():
    fake_summary = {"evaluated": 3, "expired": 1, "still_pending": 5}

    def fake_asyncio_run(coro):
        coro.close()
        outcome_resolver._resolver_running = False
        return fake_summary

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = MagicMock()
    with patch.object(outcome_resolver, "asyncio") as fake_asyncio, \
         patch.object(outcome_resolver.logger, "info") as info_log:
        fake_asyncio.run = fake_asyncio_run
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 1,
        ):
            outcome_resolver._resolver_loop()

    info_messages = []
    for call in info_log.call_args_list:
        if len(call.args) > 1:
            info_messages.append(call.args[0] % call.args[1:])
        else:
            info_messages.append(call.args[0])
    assert any(
        "evaluated=3" in m and "expired=1" in m and "still_pending=5" in m
        for m in info_messages
    )


def test_loop_catches_tick_exception_and_continues():
    """An exception during the tick is logged at error level, the loop
    continues, and the next tick proceeds normally."""
    call_count = {"n": 0}

    def fake_asyncio_run(coro):
        coro.close()
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient db lock")
        # Second tick: stop the loop.
        outcome_resolver._resolver_running = False
        return {"evaluated": 0, "expired": 0, "still_pending": 0}

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = MagicMock()
    with patch.object(outcome_resolver, "asyncio") as fake_asyncio, \
         patch.object(outcome_resolver.logger, "error") as err_log:
        fake_asyncio.run = fake_asyncio_run
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 1,
        ):
            outcome_resolver._resolver_loop()

    assert call_count["n"] == 2
    assert err_log.called


def test_loop_uses_asyncio_run_per_tick():
    """Verifies the threading-vs-asyncio choice: asyncio.run is the
    bridge between the daemon thread and the resolver's async def
    signature."""
    def fake_asyncio_run(coro):
        coro.close()
        outcome_resolver._resolver_running = False
        return {"evaluated": 0, "expired": 0, "still_pending": 0}

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = MagicMock()
    with patch.object(outcome_resolver, "asyncio") as fake_asyncio:
        fake_asyncio.run = MagicMock(side_effect=fake_asyncio_run)
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 1,
        ):
            outcome_resolver._resolver_loop()
        assert fake_asyncio.run.call_count == 1


def test_loop_responds_to_running_flag_within_one_second():
    """Loop must check _resolver_running at least once per second
    during sleep — confirms the 1s-chunk pattern is in place."""
    def fake_asyncio_run(coro):
        coro.close()
        return {"evaluated": 0, "expired": 0, "still_pending": 0}

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = MagicMock()

    # Use a real (short) thread; flip the flag after 0.5s; ensure the
    # thread exits within ~1.5s total.
    def runner():
        with patch.object(outcome_resolver, "asyncio") as fake_asyncio:
            fake_asyncio.run = fake_asyncio_run
            with patch.object(
                outcome_resolver.config,
                "OUTCOME_RESOLVER_INTERVAL_SECONDS", 5,  # would normally take 5s
            ):
                outcome_resolver._resolver_loop()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    time.sleep(0.3)
    outcome_resolver._resolver_running = False
    t.join(timeout=2.0)
    assert not t.is_alive(), (
        "loop did not respond to _resolver_running=False within 2s"
    )


# ═════════════════════════════════════════════════════════════════
# FIX-2: client-not-yet-initialized retry path
# ═════════════════════════════════════════════════════════════════


def test_loop_attempts_reconnect_when_client_is_none():
    """FIX-2: when _resolver_client is None at tick start, the loop
    calls _try_initialize_client. On success, the client is stored
    on the module-level state and evaluation proceeds on the same
    tick."""
    mock_client = MagicMock()
    init_calls = {"n": 0}

    def fake_init():
        init_calls["n"] += 1
        return mock_client

    def fake_asyncio_run(coro):
        coro.close()
        # Stop after the first evaluation so the loop exits.
        outcome_resolver._resolver_running = False
        return {"evaluated": 0, "expired": 0, "still_pending": 0}

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = None
    with patch.object(
        outcome_resolver, "_try_initialize_client", fake_init,
    ), patch.object(outcome_resolver, "asyncio") as fake_asyncio:
        fake_asyncio.run = fake_asyncio_run
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 1,
        ):
            outcome_resolver._resolver_loop()

    assert init_calls["n"] == 1
    assert outcome_resolver._resolver_client is mock_client


def test_loop_continues_retrying_when_reconnect_fails():
    """FIX-2: when _try_initialize_client returns None (e.g. ThetaData
    still unhealthy), the loop logs DEBUG, sleeps the interval, and
    retries on the next tick. _resolver_client stays None, no
    exception propagates, no resolve_pending_outcomes call."""
    init_calls = {"n": 0}

    def fake_init():
        init_calls["n"] += 1
        # Stop after 3 retry attempts.
        if init_calls["n"] >= 3:
            outcome_resolver._resolver_running = False
        return None

    asyncio_run_called = []

    def fake_asyncio_run(coro):
        coro.close()
        asyncio_run_called.append("called")
        return {}

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = None
    with patch.object(
        outcome_resolver, "_try_initialize_client", fake_init,
    ), patch.object(outcome_resolver, "asyncio") as fake_asyncio:
        fake_asyncio.run = fake_asyncio_run
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 1,
        ):
            outcome_resolver._resolver_loop()

    assert init_calls["n"] == 3
    assert outcome_resolver._resolver_client is None
    # resolve_pending_outcomes (via asyncio.run) must NOT be called
    # when the client is None — the None-check guards against it.
    assert asyncio_run_called == []


def test_loop_transitions_from_waiting_to_active_on_reconnect():
    """FIX-2: simulates the operator pre-market start scenario. First
    tick: _try_initialize_client returns None (ThetaData IV=0).
    Second tick: returns a real client (market opened, IV populates).
    Loop transitions to evaluation and calls resolve_pending_outcomes
    exactly once (only the second tick, after reconnect)."""
    mock_client = MagicMock()
    init_calls = {"n": 0}

    def fake_init():
        init_calls["n"] += 1
        if init_calls["n"] == 1:
            return None  # First tick: data not ready
        return mock_client  # Second tick: reconnected

    asyncio_run_count = {"n": 0}

    def fake_asyncio_run(coro):
        coro.close()
        asyncio_run_count["n"] += 1
        # Stop after the first successful evaluation.
        outcome_resolver._resolver_running = False
        return {"evaluated": 0, "expired": 0, "still_pending": 0}

    outcome_resolver._resolver_running = True
    outcome_resolver._resolver_client = None
    with patch.object(
        outcome_resolver, "_try_initialize_client", fake_init,
    ), patch.object(outcome_resolver, "asyncio") as fake_asyncio:
        fake_asyncio.run = fake_asyncio_run
        with patch.object(
            outcome_resolver.config,
            "OUTCOME_RESOLVER_INTERVAL_SECONDS", 1,
        ):
            outcome_resolver._resolver_loop()

    assert init_calls["n"] == 2
    assert outcome_resolver._resolver_client is mock_client
    # Only ONE evaluation: first tick was a no-op retry (client was
    # None), second tick reconnected and evaluated.
    assert asyncio_run_count["n"] == 1


# ═════════════════════════════════════════════════════════════════
# Lifespan integration
# ═════════════════════════════════════════════════════════════════


def test_lifespan_calls_start_on_startup_and_stop_on_shutdown():
    """Drive the FastAPI lifespan via TestClient context manager.
    Patch start/stop on the outcome_resolver module so we observe
    invocation without actually constructing a UnifiedDataClient."""
    from fastapi.testclient import TestClient
    from backend import app as app_module

    with patch.object(
        outcome_resolver, "start_outcome_resolver_loop",
    ) as start_mock, patch.object(
        outcome_resolver, "stop_outcome_resolver_loop",
    ) as stop_mock:
        with TestClient(app_module.app) as client:
            # Lifespan startup has run by the time we're here.
            assert start_mock.called
            # Trigger a simple request to confirm the app is alive.
            # If the lifespan startup raised, this would fail.
            _ = client
        # Lifespan shutdown has run by the time the context exits.
        assert stop_mock.called


def test_lifespan_swallows_start_exception():
    """If start_outcome_resolver_loop itself raises, the lifespan logs
    and continues — FastAPI must still come up."""
    from fastapi.testclient import TestClient
    from backend import app as app_module

    with patch.object(
        outcome_resolver, "start_outcome_resolver_loop",
        side_effect=RuntimeError("boom"),
    ), patch.object(
        outcome_resolver, "stop_outcome_resolver_loop",
    ):
        with TestClient(app_module.app):
            pass  # If lifespan re-raised, this would fail.
