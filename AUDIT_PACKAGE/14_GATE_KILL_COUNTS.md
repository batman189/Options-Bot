# 14. Gate Kill Counts

## Signal Log Analysis (1,557 total signal log entries)

### Stop Step Distribution

| Step | Gate Name | Count | % of Total |
|------|-----------|-------|------------|
| 0 | Equity gate ($25K PDT) | ~98 | 6.3% |
| 0 | Portfolio exposure limit | unknown | — |
| 0 | Auto-pause (errors) | 0 | 0% |
| 0 | No model loaded | 0 | 0% |
| 1 | Price unavailable | 0 | 0% |
| 1 | VIX gate outside range | ~25 | 1.6% |
| 2 | No historical bars | unknown | — |
| 4 | Feature computation failed | unknown | — |
| 5 | Prediction failed / NaN | unknown | — |
| 6 | Confidence below threshold | ~480+ | 30.8% |
| 7 | Backtest long-only skip | unknown | — |
| 8 | PDT limit | unknown | — |
| 8.5 | Implied move gate | N/A (classifier bypass) | — |
| 8.7 | Earnings blackout | 0 (all OK) | 0% |
| 9 | No contract meets EV | 39 | 2.5% |
| 9.5 | Liquidity reject | 34 | 2.2% |
| 9.7 | Portfolio delta limit | unknown | — |
| 10 | Risk check / sizing | unknown | — |
| NULL | Trade entered | 3 | 0.2% |

### Top Stop Reasons (from DB GROUP BY)

1. **confidence 0.000 < 0.6 threshold** — 164 entries (TSLA swing profile, likely from before min_confidence was lowered)
2. **Scalp equity gate** — ~98 entries across multiple equity values ($24,803-$24,864 < $25,000)
3. **No contract meets EV threshold** — 39 entries
4. **Liquidity reject (volume < 50)** — 34 entries
5. **Confidence below 0.1** — ~300+ entries (scalp, various low confidence values)
6. **VIX gate outside range** — ~25 entries

### Funnel Analysis (Today's Scalp Session)

```
Iterations:           49
→ Equity gate pass:   49  (portfolio > $25K today)
→ VIX gate pass:      49  (VIXY=31.75, range [12, 50])
→ Bars available:     49
→ Features computed:  49
→ Prediction OK:      49
→ Confidence >= 0.1:  ~40  (some < 0.1 filtered)
→ Earnings OK:        ~40
→ EV contract found:  ~40  (some iterations no qualifying contract)
→ Liquidity pass:     1   ← MASSIVE DROPOFF
→ Risk check pass:    1
→ TRADE ENTERED:      1   (7 contracts SPY 666 PUT $0.08)
```

**Key insight**: The funnel narrows catastrophically at the liquidity gate. 98% of selected contracts have daily_volume=1 or 0. This means the EV filter is selecting contracts that do not trade.

### Historical Entry Rate
- 1,557 signal logs total
- 3 trades entered (entered=1)
- **Entry rate: 0.19%** — less than 1 in 500 signals result in a trade
