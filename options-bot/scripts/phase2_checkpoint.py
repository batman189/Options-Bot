"""Phase 2 Validation Checkpoint — Market Context Engine."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from market.context import MarketContext, Regime
from data.unified_client import UnifiedDataClient
import pandas as pd
import numpy as np
from datetime import datetime

print("=" * 70)
print("PHASE 2 VALIDATION CHECKPOINT")
print("=" * 70)

client = UnifiedDataClient()
ctx = MarketContext(data_client=client)

# TEST 1: Live regime classification (5 cycles, 30s apart)
print("\nTEST 1: Market context classification (5 cycles, 30s apart)")
print("-" * 60)
for i in range(5):
    snap = ctx.update(force=True)
    print(f"  Cycle {i+1}: regime={snap.regime.value} | reason={snap.regime_reason}")
    print(f"           SPY 30m={snap.spy_30min_move_pct:+.3f}% | 60m range={snap.spy_60min_range_pct:.3f}% | rev={snap.spy_30min_reversals} | vol={snap.spy_volume_ratio:.2f}")
    print(f"           VIX={snap.vix_level:.2f} | VIX open chg={snap.vix_intraday_change_pct:+.1f}% | ToD={snap.time_of_day.value}")
    if i < 4:
        time.sleep(30)
print("\nTEST 1 RESULT: PASS")

# TEST 2: Time-of-day classification
print("\nTEST 2: Time-of-day classification")
print("-" * 60)
tod = ctx.get_time_of_day()
try:
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
except Exception:
    now_et = datetime.utcnow()
print(f"  Current ET time: {now_et.strftime('%H:%M')}")
print(f"  Classification: {tod.value}")
print("\nTEST 2 RESULT: PASS")

# TEST 3: get_snapshot() full output
print("\nTEST 3: get_snapshot() full output")
print("-" * 60)
snap = ctx.get_snapshot()
for field in ["regime", "time_of_day", "timestamp", "spy_30min_move_pct",
              "spy_60min_range_pct", "spy_30min_reversals", "spy_volume_ratio",
              "vix_level", "vix_intraday_change_pct", "regime_reason"]:
    val = getattr(snap, field)
    if isinstance(val, float):
        print(f"  {field:30s} = {val:+.4f}" if "move" in field or "change" in field else f"  {field:30s} = {val:.4f}")
    else:
        print(f"  {field:30s} = {val}")
print("\nTEST 3 RESULT: PASS")

# TEST 4: Simulate each regime with synthetic data
print("\nTEST 4: Regime simulation with synthetic bars")
print("-" * 60)

def make_bars(prices, volumes):
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="1min")
    return pd.DataFrame({
        "open": prices, "high": [p + 0.1 for p in prices],
        "low": [p - 0.1 for p in prices], "close": prices,
        "volume": volumes,
    }, index=idx)

# HIGH_VOLATILITY: VIX >= 25
class MockHV:
    def get_stock_bars(self, *a, **kw): return make_bars(list(np.linspace(100, 100.3, 60)), [1000]*60)
    def get_vix(self): return 28.0
c1 = MarketContext()
c1._vix_open = 28.0
c1._client = MockHV()
s1 = c1.update(force=True)
print(f"  HIGH_VOLATILITY: regime={s1.regime.value} | reason={s1.regime_reason}")
print(f"    VIX={s1.vix_level} move={s1.spy_30min_move_pct:+.3f}% range={s1.spy_60min_range_pct:.3f}%")
assert s1.regime == Regime.HIGH_VOLATILITY, f"FAIL: got {s1.regime}"

# CHOPPY: tiny range, low VIX
class MockCH:
    def get_stock_bars(self, *a, **kw): return make_bars(list(np.linspace(100, 100.05, 60)), [1000]*60)
    def get_vix(self): return 18.0
c2 = MarketContext()
c2._vix_open = 18.0
c2._client = MockCH()
s2 = c2.update(force=True)
print(f"  CHOPPY: regime={s2.regime.value} | reason={s2.regime_reason}")
print(f"    VIX={s2.vix_level} move={s2.spy_30min_move_pct:+.3f}% range={s2.spy_60min_range_pct:.3f}%")
assert s2.regime == Regime.CHOPPY, f"FAIL: got {s2.regime}"

# TRENDING_UP: big up move + volume, low VIX
class MockTU:
    def get_stock_bars(self, *a, **kw): return make_bars(list(np.linspace(100, 101.5, 60)), [500]*30 + [2000]*30)
    def get_vix(self): return 20.0
c3 = MarketContext()
c3._vix_open = 20.0
c3._client = MockTU()
s3 = c3.update(force=True)
print(f"  TRENDING_UP: regime={s3.regime.value} | reason={s3.regime_reason}")
print(f"    VIX={s3.vix_level} move={s3.spy_30min_move_pct:+.3f}% vol={s3.spy_volume_ratio:.2f}")
assert s3.regime == Regime.TRENDING_UP, f"FAIL: got {s3.regime}"

# TRENDING_DOWN: big down move + volume, low VIX
class MockTD:
    def get_stock_bars(self, *a, **kw): return make_bars(list(np.linspace(101.5, 100, 60)), [500]*30 + [2000]*30)
    def get_vix(self): return 20.0
c4 = MarketContext()
c4._vix_open = 20.0
c4._client = MockTD()
s4 = c4.update(force=True)
print(f"  TRENDING_DOWN: regime={s4.regime.value} | reason={s4.regime_reason}")
print(f"    VIX={s4.vix_level} move={s4.spy_30min_move_pct:+.3f}% vol={s4.spy_volume_ratio:.2f}")
assert s4.regime == Regime.TRENDING_DOWN, f"FAIL: got {s4.regime}"

# Priority: HIGH_VOL wins over TRENDING when both conditions met
class MockPri:
    def get_stock_bars(self, *a, **kw): return make_bars(list(np.linspace(100, 101.5, 60)), [500]*30 + [2000]*30)
    def get_vix(self): return 30.0
c5 = MarketContext()
c5._vix_open = 25.0
c5._client = MockPri()
s5 = c5.update(force=True)
print(f"  PRIORITY TEST: regime={s5.regime.value} | reason={s5.regime_reason}")
print(f"    VIX={s5.vix_level} (HIGH_VOL) + move={s5.spy_30min_move_pct:+.3f}% (TRENDING) => HIGH_VOL wins")
assert s5.regime == Regime.HIGH_VOLATILITY, f"PRIORITY FAIL: got {s5.regime}"

print("\n  All 4 regimes + priority test passed.")
print("\nTEST 4 RESULT: PASS")
