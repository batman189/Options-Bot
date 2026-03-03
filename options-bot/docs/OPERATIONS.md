# Options Bot — Operations Runbook

## Daily Checks

1. **Check Dashboard** — Open http://localhost:3000
   - All profiles show "active" status
   - No red model health banners
   - PDT counter within limits
   - Alpaca and Theta connected (green dots)

2. **Check logs** — Look for warnings/errors
   ```bash
   tail -100 logs/live_*.log | grep -i "error\|warning\|fail\|auto-paused"
   ```

3. **Check trading processes** — from System page or API:
   ```bash
   curl http://localhost:8000/api/trading/status | python -m json.tool
   ```

---

## Common Operations

### "Why didn't the bot trade today?"

1. Open Profile Detail → Signal Log panel
2. Look at recent entries — each shows the step where it stopped and why
3. Common reasons:
   - Step 5: "Model prediction is NaN" → model needs retraining
   - Step 6: "Below threshold" → market not volatile enough
   - Step 8: "PDT limit reached" → wait for rolling window to clear
   - Step 9: "No valid EV contract" → no options meeting EV criteria
   - Step 10: "Position limit reached" → at max concurrent positions

### "Model accuracy is dropping"

1. Check Profile Detail → Live Accuracy tile
2. If below 45%: model is degraded
3. Actions:
   - Retrain: Profile Detail → Train (fresh model on recent data)
   - Check data: `python scripts/validate_data.py`
   - Review regime: market may have changed (mean-reverting → trending)

### "Add a new trading symbol"

1. Verify symbol has options: `curl "http://localhost:25503/v3/stock/list/symbols" | grep SYMBOL`
2. Verify Alpaca has data: test in `python scripts/validate_data.py`
3. Create a new profile in the UI with the symbol
4. Train a model for the new profile
5. Activate when ready

### "Force retrain a model"

1. UI: Profile Detail → Train button → select model type → click Train
2. API: `curl -X POST http://localhost:8000/api/models/{profile_id}/train -H "Content-Type: application/json" -d '{"force_full_retrain": true}'`
3. Monitor progress in the Training Logs panel

### "Backup and restore"

```bash
# Backup
mkdir -p backups
cp db/options_bot.db backups/options_bot_$(date +%Y%m%d_%H%M%S).db
cp -r models/ backups/models_$(date +%Y%m%d_%H%M%S)/

# Restore
cp backups/options_bot_YYYYMMDD.db db/options_bot.db
cp -r backups/models_YYYYMMDD/* models/
python main.py  # Restart
```

### "Reset a stuck profile"

If a profile is stuck in "training" or "error":
```bash
# Option 1: Restart the backend (auto-resets stuck profiles)
# Kill and restart main.py

# Option 2: Manual DB fix
python -c "
import sqlite3
conn = sqlite3.connect('db/options_bot.db')
conn.execute(\"UPDATE profiles SET status = 'ready' WHERE id = 'PROFILE_ID'\")
conn.commit()
conn.close()
"
```

### "Emergency: Close all positions"

The emergency stop loss triggers automatically at 20% portfolio drawdown, but to manually close everything:

1. UI: Dashboard → Pause All (per-profile buttons)
2. Or directly via Alpaca dashboard: https://app.alpaca.markets → close all positions

---

## Health Monitoring

### Key Metrics to Watch

| Metric | Where | Healthy | Warning | Action |
|--------|-------|---------|---------|--------|
| Model accuracy | Dashboard banner | >52% | <45% | Retrain |
| Model age | Profile Detail | <30 days | >30 days | Retrain |
| Consecutive errors | Logs | 0 | >5 | Check logs |
| Circuit breaker | Logs | Closed | Open | Wait or restart service |
| PDT trades used | Dashboard | <3 | =3 | Stop day trading |
| Portfolio exposure | Dashboard | <60% | >60% | Close positions |

### Watchdog Behavior

The backend includes an automatic watchdog that:
- Checks trading subprocesses every 30 seconds
- Auto-restarts crashed processes (up to 3 times)
- Logs all restarts to the training_logs table
- Sets profile status to "error" after 3 failed restart attempts

Check watchdog status:
```bash
curl http://localhost:8000/api/trading/watchdog-stats | python -m json.tool
```
