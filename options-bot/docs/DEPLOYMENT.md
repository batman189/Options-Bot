# Options Bot — Deployment Guide

## Prerequisites

### Hardware
- CPU: 4+ cores recommended (TFT training is CPU-intensive)
- RAM: 8 GB minimum, 16 GB recommended (TFT + PyTorch needs ~4 GB)
- Disk: 5 GB free (models ~200 MB, data cache ~500 MB, logs ~50 MB)
- Network: Stable internet connection (Alpaca WebSocket, Theta Terminal)

### Software
- Python 3.10 or 3.11 (3.12+ not tested with pytorch-forecasting)
- Java 17+ (for Theta Data Terminal)
- Node.js 18+ and npm (for UI build)
- Git

### Accounts
- **Alpaca**: Algo Trader Plus plan ($99/mo) — required for real-time SIP data
  - Paper account for testing: https://app.alpaca.markets
  - API key + secret from the dashboard
- **Theta Data**: Options Standard plan (~$30/mo) — required for options Greeks/chains
  - Download Theta Terminal v3 JAR: https://www.thetadata.net
  - Username + password for creds.txt

---

## Step 1: Clone and Install

```bash
git clone <repo-url> options-bot
cd options-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate    # Linux/macOS
# venv\Scripts\activate     # Windows

# Install Python dependencies
pip install -r requirements.txt

# Install UI dependencies
cd ui
npm install
npm run build
cd ..
```

**Note**: PyTorch (~2 GB) is included in requirements.txt. First install may take 10-15 minutes.

---

## Step 2: Configure Environment

Copy the template and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:
- `ALPACA_API_KEY` — from Alpaca dashboard
- `ALPACA_API_SECRET` — from Alpaca dashboard
- `ALPACA_PAPER=true` — keep true until proven profitable
- `THETADATA_USERNAME` — Theta Data account email
- `THETADATA_PASSWORD` — Theta Data account password

---

## Step 3: Start Theta Terminal

Theta Terminal must be running before training models or live trading.

```bash
# Create creds.txt in the Theta Terminal directory:
echo "your_email@example.com" > creds.txt
echo "your_password" >> creds.txt

# Start Theta Terminal
java -jar ThetaTerminalv3.jar
```

Theta Terminal runs on `localhost:25503` by default. Override with `THETA_TERMINAL_HOST` and `THETA_TERMINAL_PORT` in `.env` if needed.

---

## Step 4: Run Pre-flight Check

```bash
python scripts/startup_check.py
```

This verifies: Python version, dependencies, .env config, database, disk space, Alpaca connection, and Theta Terminal connection. Fix any FAIL items before proceeding.

---

## Step 5: Start the Bot

### Backend only (for UI management, model training):
```bash
python main.py
```
- Backend: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- UI: http://localhost:3000 (run `npm run dev` in `ui/` for development)

### Backend + trading (single profile):
```bash
python main.py --trade --profile-id <uuid>
```

### Backend + trading (multiple profiles):
```bash
python main.py --trade --profile-ids <uuid1> <uuid2> <uuid3>
```

### Recommended: Use the UI
1. Start backend: `python main.py`
2. Open UI: http://localhost:3000
3. Create a profile (Profiles → Create)
4. Train a model (Profile Detail → Train XGBoost)
5. Activate trading (Profile Detail → Activate)

The UI uses `/api/trading/start` and `/api/trading/stop` which spawn subprocesses automatically.

---

## Step 6: Production Deployment (Linux systemd)

### Service file: `/etc/systemd/system/options-bot.service`

```ini
[Unit]
Description=Options Bot Trading System
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/options-bot
Environment=PATH=/home/trader/options-bot/venv/bin
ExecStart=/home/trader/options-bot/venv/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable options-bot
sudo systemctl start options-bot

# Check status
sudo systemctl status options-bot
journalctl -u options-bot -f
```

### Service file for Theta Terminal: `/etc/systemd/system/theta-terminal.service`

```ini
[Unit]
Description=Theta Data Terminal
After=network.target
Before=options-bot.service

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/theta-terminal
ExecStart=/usr/bin/java -jar ThetaTerminalv3.jar
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

### Windows Task Scheduler

1. Open Task Scheduler → Create Task
2. Trigger: At system startup
3. Action: Start a program
   - Program: `C:\Users\you\options-bot\venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\Users\you\options-bot`
4. Conditions: Start only if network is available
5. Settings: If task fails, restart every 1 minute (up to 3 times)

---

## Log Files

| Location | Contents |
|----------|----------|
| `logs/live_YYYYMMDD_HHMMSS.log` | Main process log (rotated at 10 MB, 5 backups) |
| `logs/backtest_debug_*.log` | Backtest output |
| `db/options_bot.db` → `training_logs` table | Training logs (visible in System UI) |

---

## Database

SQLite database at `db/options_bot.db`. No external database server needed.

### Backup
```bash
# Simple file copy (stop trading first for consistency)
cp db/options_bot.db db/options_bot_backup_$(date +%Y%m%d).db
```

### Reset (delete all data)
```bash
rm db/options_bot.db
python main.py  # Recreates schema on startup
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Alpaca API key not configured" | Missing .env | Copy .env.example to .env and fill in keys |
| "Cannot connect to Theta Terminal" | Theta not running | Start `java -jar ThetaTerminalv3.jar` |
| "No bars returned for TSLA" | Market closed / API issue | Wait for market hours or check Alpaca status |
| Profile stuck in "training" | Process killed mid-train | Restart backend — auto-resets on startup |
| "Circuit breaker OPEN" | External service down | Wait for auto-reset (2-5 min) or restart |
| Port 8000 already in use | Previous process | `kill $(lsof -t -i:8000)` or restart |
| UI shows no data | Backend not running | Start `python main.py` first |
| "AUTO-PAUSED: 10 consecutive errors" | Repeated failures | Check logs, fix root cause, restart profile |
