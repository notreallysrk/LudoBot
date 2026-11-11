# Ludo Arena — Phase 1

Phase 1 starter: Aiogram 3 Bot client + FastAPI webhook + MongoDB + Telegram `sendWidget` home menu.

## Included
- `/start` registers/updates the Telegram user in MongoDB and sends the Ludo Arena HTML widget.
- `/help` responds with basic help.
- Widget buttons send small `widget_query` actions; the bot acknowledges them and logs taps in MongoDB.
- Health endpoint: `/health`.
- Same codebase supports Heroku and a Linux VPS via environment variables.

> Phase 1 buttons are wired and return clear phase-status messages. Actual Ludo matches, AI, matchmaking, wallet transfers and leaderboard logic are intentionally scheduled for later phases. The widget is a compact, CSS-rendered approximation of the supplied visual reference because Telegram widgets have strict HTML/compression limits and no network access.

## Requirements
- Python 3.12+
- MongoDB Atlas or self-hosted MongoDB reachable from the host
- Telegram bot token from @BotFather
- Public HTTPS URL for webhook hosting

## Local/VPS setup
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
mkdir -p /opt/ludo-arena
# Upload/copy this project into /opt/ludo-arena
cd /opt/ludo-arena
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```
Set `BOT_TOKEN`, `MONGODB_URI`, `WEBHOOK_BASE_URL` (public HTTPS URL) and a long random `WEBHOOK_SECRET`.

Run manually:
```bash
. venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

For systemd, edit `deploy/ludo-arena.service` if your Linux username/path differs, then:
```bash
sudo cp deploy/ludo-arena.service /etc/systemd/system/ludo-arena.service
sudo systemctl daemon-reload
sudo systemctl enable --now ludo-arena
sudo journalctl -u ludo-arena -f
```
Put Nginx/Caddy/Cloudflare Tunnel in front so Telegram can reach the HTTPS webhook.

## Heroku
1. Create a Heroku app and connect this GitHub repository.
2. Add Config Vars: `BOT_TOKEN`, `MONGODB_URI`, `MONGODB_DB`, `WEBHOOK_BASE_URL=https://YOUR-APP.herokuapp.com`, `WEBHOOK_SECRET`, `ENVIRONMENT=production`.
3. Deploy the branch. The `Procfile` starts the FastAPI web process.
4. Check `https://YOUR-APP.herokuapp.com/health`.

Do not run two webhook instances with the same bot token at the same time. For simultaneous Heroku/VPS testing, use separate bot tokens (separate test bot) or stop the webhook on one host before switching.

## Notes about Telegram Widgets
- `sendWidget` is used for `/start`.
- Widgets are currently production-supported in private bot chats; group/inline/forward scenarios are not assumed.
- Widget HTML is fixed when sent. To change the UI, update `widget/home.html` and send a new widget message.
- Widget JavaScript cannot fetch your API directly. It uses `TelegramWidget.request()`; the bot receives `widget_query` and responds with `answerWidgetQuery`.
- The 64-byte widget request payload is kept to short action names.

## Security
- Never commit `.env` or share your bot token/MongoDB URI.
- Use a unique webhook secret and HTTPS.
- MongoDB user should have access only to the app database.
