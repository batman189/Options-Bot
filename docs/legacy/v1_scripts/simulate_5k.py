"""
Monte Carlo simulation of all 4 bot profiles on a $5,000 account.
Run: python scripts/simulate_5k.py
"""
import numpy as np
np.random.seed(42)

STARTING_CAPITAL = 5_000
NUM_SIMS = 5000
MONTHS = 6
DAYS_PER_MONTH = 21

# --- PROFILE 1: SPY Iron Condor (0DTE premium selling) ---
IC_CREDIT = 55
IC_WIN_PNL = 41.25       # 75% of credit
IC_LOSS_PNL = -55         # 1x credit stop
IC_WIN_RATE = 0.72
IC_MAX_LOSS_CONTRACT = 245
IC_RISK_PCT = 5.0
IC_FAVORABLE_RATE = 0.60
IC_TRADES_PER_DAY = 1.3

# --- PROFILE 2: SPY OTM (gamma explosion) ---
OTM_WIN_RATE = 0.15
OTM_AVG_COST = 8
OTM_CONTRACTS = 50
OTM_WIN_MULTIPLIER = 8.0
OTM_TRADES_PER_MONTH = 3

# --- PROFILE 3: TSLA Swing (aggressive directional 7-45 DTE) ---
TSLA_WIN_RATE = 0.55
TSLA_AVG_ENTRY = 1500
TSLA_WIN_PNL_PCT = 0.40    # Bigger wins — trailing stop lets winners run to +40% avg
TSLA_LOSS_PNL_PCT = -0.12  # 12% stop loss, tight cut
TSLA_RISK_PCT = 30.0       # Aggressive — 30% of capital
TSLA_TRADES_PER_MONTH = 3  # Fewer but higher conviction (0.30 threshold)

# --- PROFILE 4: SPY Scalp (aggressive ATM 0DTE directional) ---
SCALP_WIN_RATE = 0.50       # Near coin-flip but trailing stop improves payoff
SCALP_AVG_ENTRY = 150
SCALP_WIN_PNL_PCT = 0.30    # Trailing stop lets 0DTE momentum run
SCALP_LOSS_PNL_PCT = -0.15  # 15% stop
SCALP_RISK_PCT = 25.0       # Aggressive
SCALP_TRADES_PER_DAY = 2
SCALP_FAVORABLE_RATE = 0.35  # Only 35% of days (high confidence 0.25 required)

print("=" * 70)
print(f"COMBINED BOT SIMULATION - ${STARTING_CAPITAL:,} ACCOUNT - {MONTHS} MONTHS")
print(f"Simulations: {NUM_SIMS}")
print("=" * 70)

all_finals = []
all_drawdowns = []
monthly_snapshots = np.zeros((NUM_SIMS, MONTHS))

for sim in range(NUM_SIMS):
    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0

    for month in range(MONTHS):
        for day in range(DAYS_PER_MONTH):
            # Iron Condor
            if np.random.random() < IC_FAVORABLE_RATE:
                n = max(1, min(2, int(np.random.poisson(IC_TRADES_PER_DAY))))
                for _ in range(n):
                    qty = max(1, int(capital * IC_RISK_PCT / 100 / IC_MAX_LOSS_CONTRACT))
                    if np.random.random() < IC_WIN_RATE:
                        capital += IC_WIN_PNL * qty
                    else:
                        capital += IC_LOSS_PNL * qty

            # SPY Scalp
            if np.random.random() < SCALP_FAVORABLE_RATE:
                n = max(1, min(3, int(np.random.poisson(SCALP_TRADES_PER_DAY))))
                for _ in range(n):
                    risk = capital * SCALP_RISK_PCT / 100
                    qty = max(1, int(risk / SCALP_AVG_ENTRY))
                    if np.random.random() < SCALP_WIN_RATE:
                        capital += SCALP_AVG_ENTRY * qty * SCALP_WIN_PNL_PCT
                    else:
                        capital += SCALP_AVG_ENTRY * qty * SCALP_LOSS_PNL_PCT

            if capital > peak:
                peak = capital
            dd = (peak - capital) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
            if capital <= 0:
                capital = 0
                break

        if capital <= 0:
            break

        # SPY OTM (monthly)
        otm_trades = min(3, np.random.poisson(OTM_TRADES_PER_MONTH))
        for _ in range(otm_trades):
            max_otm_spend = capital * 0.10
            qty = max(1, min(OTM_CONTRACTS, int(max_otm_spend / OTM_AVG_COST)))
            cost = OTM_AVG_COST * qty
            if np.random.random() < OTM_WIN_RATE:
                capital += cost * (OTM_WIN_MULTIPLIER - 1)
            else:
                capital -= cost

        # TSLA Swing (monthly)
        tsla_trades = min(6, np.random.poisson(TSLA_TRADES_PER_MONTH))
        for _ in range(tsla_trades):
            risk = capital * TSLA_RISK_PCT / 100
            if risk < 500:
                continue
            qty = max(1, int(risk / TSLA_AVG_ENTRY))
            cost = TSLA_AVG_ENTRY * qty
            if np.random.random() < TSLA_WIN_RATE:
                capital += cost * TSLA_WIN_PNL_PCT
            else:
                capital += cost * TSLA_LOSS_PNL_PCT

        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

        monthly_snapshots[sim, month] = capital

    all_finals.append(capital)
    all_drawdowns.append(max_dd)

finals = np.array(all_finals)
dds = np.array(all_drawdowns)

print()
print("ACCOUNT VALUE AFTER 6 MONTHS:")
for label, val in [
    ("Median", np.median(finals)),
    ("Mean", np.mean(finals)),
    ("10th pct", np.percentile(finals, 10)),
    ("25th pct", np.percentile(finals, 25)),
    ("75th pct", np.percentile(finals, 75)),
    ("90th pct", np.percentile(finals, 90)),
    ("Best", np.max(finals)),
    ("Worst", np.min(finals)),
]:
    pct = (val / STARTING_CAPITAL - 1) * 100
    print(f"  {label:12} ${val:>10,.0f}  ({pct:+.0f}%)")

print()
print("RISK METRICS:")
print(f"  Avg max drawdown:      {np.mean(dds):.1f}%")
print(f"  Median max drawdown:   {np.median(dds):.1f}%")
print(f"  Worst max drawdown:    {np.max(dds):.1f}%")
print(f"  Prob profitable:       {(finals > STARTING_CAPITAL).mean()*100:.1f}%")
print(f"  Prob >25% gain:        {(finals > STARTING_CAPITAL * 1.25).mean()*100:.1f}%")
print(f"  Prob >50% gain:        {(finals > STARTING_CAPITAL * 1.50).mean()*100:.1f}%")
print(f"  Prob >100% gain:       {(finals > STARTING_CAPITAL * 2.0).mean()*100:.1f}%")
print(f"  Prob lose >20%:        {(finals < STARTING_CAPITAL * 0.8).mean()*100:.1f}%")
print(f"  Prob lose >50%:        {(finals < STARTING_CAPITAL * 0.5).mean()*100:.1f}%")
print(f"  Prob blown (<$500):    {(finals < 500).mean()*100:.1f}%")

print()
print("MONTHLY PROGRESSION:")
print(f"  {'':8} {'Median':>10} {'25th pct':>10} {'75th pct':>10}")
for m in range(MONTHS):
    med = np.median(monthly_snapshots[:, m])
    p25 = np.percentile(monthly_snapshots[:, m], 25)
    p75 = np.percentile(monthly_snapshots[:, m], 75)
    print(f"  Month {m+1}: ${med:>8,.0f}   ${p25:>8,.0f}   ${p75:>8,.0f}")

print()
print("PER-PROFILE EV:")
ic_ev = IC_WIN_RATE * IC_WIN_PNL + (1-IC_WIN_RATE) * IC_LOSS_PNL
scalp_ev = SCALP_WIN_RATE * SCALP_AVG_ENTRY * SCALP_WIN_PNL_PCT + (1-SCALP_WIN_RATE) * SCALP_AVG_ENTRY * SCALP_LOSS_PNL_PCT
otm_ev = OTM_WIN_RATE * OTM_AVG_COST * OTM_CONTRACTS * (OTM_WIN_MULTIPLIER-1) - (1-OTM_WIN_RATE) * OTM_AVG_COST * OTM_CONTRACTS
tsla_ev = TSLA_WIN_RATE * TSLA_AVG_ENTRY * TSLA_WIN_PNL_PCT + (1-TSLA_WIN_RATE) * TSLA_AVG_ENTRY * TSLA_LOSS_PNL_PCT
print(f"  Iron Condor:  EV = ${ic_ev:+.2f}/trade")
print(f"  SPY Scalp:    EV = ${scalp_ev:+.2f}/trade")
print(f"  SPY OTM:      EV = ${otm_ev:+.2f}/batch ({OTM_CONTRACTS} contracts)")
print(f"  TSLA Swing:   EV = ${tsla_ev:+.2f}/trade")

print()
print("ASSUMPTIONS:")
print("  - IC 72% WR from Option Alpha / Early Retirement Now 0DTE research")
print("  - Scalp 48% WR conservative (model 62.7% minus real-world friction)")
print("  - OTM 15% WR (most gamma plays expire worthless)")
print("  - TSLA 55% WR (model 78.7% minus theta/spread drag on options)")
print("  - Bid-ask spread partially modeled via reduced win rates")
print("  - Black swan events not modeled")
print("  - $5K constrains position sizing to 1 contract on many trades")
print("  - GEX regime filter effectiveness unproven")
