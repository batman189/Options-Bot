# Capital Requirements by Profile

## Overview

Each strategy type has a minimum account equity to activate. This is enforced in the UI — profiles below their minimum show a locked state with the requirement displayed. As the account grows, profiles automatically become available.

---

## Tier 1: $5,000 Minimum

### Momentum Scalp
- **Why $5K works:** ATM SPY 0DTE options cost $1-3 per contract. At 25% sizing ($1,250), you can buy 4-8 contracts. Wins of +40-80% = $500-1,000 per trade. Losses of -15% = $187. The math works at this level.
- **Constraints at $5K:** Limited to 4-8 contracts. Can't scale into positions. One bad day (-5% account = $250) is recoverable.
- **Sweet spot:** $5K-25K

### Swing
- **Why $5K works:** TSLA options at $10-20 per contract. At 25% sizing ($1,250), you buy 1 contract. Wins of +30-60% = $375-750. Losses of -20% (underlying stop) = ~$250. Thin margin but viable.
- **Constraints at $5K:** Limited to 1 contract per trade. No diversification across symbols — one swing trade at a time. Picking the right single trade matters a lot.
- **Sweet spot:** $10K-50K (2-3 contracts allows for better risk distribution)

---

## Tier 2: $10,000 Minimum

### OTM Gamma
- **Why $10K:** At 10% sizing ($1,000), you buy 20-100 contracts of $0.10-0.50 options. Max 3 trades/day = $3,000 max daily risk (30% of account). That's aggressive but the asymmetric payoff (3x-20x on winners) covers losses over time. At $5K, 3 losing trades in a day ($1,500 = 30%) is too close to the edge.
- **Constraints at $10K:** Still can't size as heavily as the $41K SPY put trader. But 50 contracts at $0.10 = $500 risk, and a 10x spike = $5,000. That's life-changing at this account size.
- **Sweet spot:** $10K-50K

---

## Tier 3: $25,000 Minimum

### Iron Condor
- **Why $25K:** Two reasons. First, PDT rule — Alpaca requires $25K for unlimited day trades on real accounts. Iron condors open and close same day (0DTE), so they count as day trades. Second, math — at 5% sizing ($1,250) with $245 max loss per contract, you can run 5 contracts. 5 contracts × $41 avg win = $205/day on winning days. At $5K you'd run 1 contract for $41/day — not worth the complexity.
- **Constraints at $25K:** 5-10 contracts per trade. Steady income profile. This is the "base salary" of the bot — consistent small wins that compound.
- **Sweet spot:** $25K-100K+

---

## Summary Table

| Strategy Type | Min Capital | Sizing | Contracts | Max Daily Risk | Reason |
|---|---|---|---|---|---|
| Momentum Scalp | $5,000 | 25% | 4-8 | ~$625 (12.5%) | ATM options are affordable, good risk/reward at any size |
| Swing | $5,000 | 25% | 1-3 | ~$250 (5%) | Works with 1 contract, better at $10K+ |
| OTM Gamma | $10,000 | 10% | 20-100 | ~$3,000 (30%) | Needs room for 3 daily losses without blowing up |
| Iron Condor | $25,000 | 5% | 5-10 | ~$1,225 (5%) | PDT rule + need 5+ contracts for meaningful income |

---

## UI Display

On the Profiles tab, each strategy type in the "New Profile" selector shows:

```
[Momentum Scalp]                              ✓ Available
 Rides strong intraday moves on 0DTE options.
 Minimum: $5,000 | Your equity: $5,000

[Swing]                                       ✓ Available
 Multi-day directional trades, 7-45 DTE.
 Minimum: $5,000 | Your equity: $5,000

[OTM Gamma]                                   🔒 Locked
 Buys cheap far-OTM for rare explosive moves.
 Minimum: $10,000 | Your equity: $5,000 | Need: $5,000 more

[Iron Condor]                                 🔒 Locked
 Sells premium in range-bound markets.
 Minimum: $25,000 | Your equity: $5,000 | Need: $20,000 more
```

Locked profiles are visible but not selectable. The user can see what's coming as their account grows. This creates a natural progression:

1. **$5K:** Start with Momentum Scalp + Swing. Build the account.
2. **$10K:** Unlock OTM Gamma. Add the lottery ticket strategy.
3. **$25K:** Unlock Iron Condor. Add steady premium income. Also unlocks unlimited day trades on real accounts (PDT).

---

## Enforcement

- Checked at profile creation time (can't create a profile you can't fund)
- Checked at trading start time (if account dropped below minimum since creation, show warning and block)
- Checked on every trading iteration (if account drops below 80% of minimum mid-day, warn but don't force-close existing positions — just block new entries)
- The equity check reads from Alpaca's account endpoint, not our DB (real-time accuracy)

---

## Override for Paper Trading

On paper accounts, the minimums should be enforceable but with a user override. A paper trader might want to test Iron Condor logic with $5K paper money to understand how it works before funding a real $25K account.

UI: "This profile requires $25,000 minimum equity. Your paper account has $5,000. [Create Anyway — Paper Only]"

The override button is only visible on paper accounts. Real accounts enforce hard minimums with no override.

---

## Adjustments Over Time

These minimums are starting points based on:
- Position sizing math
- Maximum daily drawdown tolerance
- Minimum contract counts for the strategy to make sense
- PDT rule for real accounts

After 1-2 months of live data, we may adjust. If Momentum Scalp proves to work well at $3K, we lower the minimum. If OTM Gamma needs more cushion, we raise it. The numbers are stored in config, not hardcoded.
