# funbot

A small Discord bot: occasional fun replies, activity tracking (messages + voice time), `!mystats` / `!leaderboard`, and a daily "Throwback of the Day".

Only three dependencies: `discord.py`, `asyncpg`, `python-dotenv`. Tables are created automatically on first start.

## Commands

| Command | Who | What |
|---|---|---|
| `!mystats` | anyone | your messages, voice time and ranks |
| `!leaderboard [messages\|voice\|combined]` (`!lb`) | anyone | top 10 (combined = messages + voice minutes) |
| `!backfill` | administrators | import the server's existing message history (run once) |
| `!throwback` | Manage Server | post a throwback right now |

Mentioning the bot always gets a reply. Keyword replies are limited to one per channel every 5 minutes, and fire about half the time.

## 1. Discord setup

1. https://discord.com/developers/applications → New Application → **Bot** tab → copy the token.
2. On the same tab enable **Message Content Intent** (the bot will not start without it).
3. **OAuth2 → URL Generator**: scope `bot`; permissions: View Channels, Send Messages, Read Message History, Embed Links. Open the URL to invite the bot.
4. In Discord, enable Developer Mode (Settings → Advanced), right-click the throwback channel → Copy Channel ID.

## 2. Run locally (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in DISCORD_TOKEN and DATABASE_URL
python main.py
```

## 3. Deploy on Railway

1. Put this folder in a GitHub repo (the folder root must contain `main.py` and `requirements.txt`) and create a Railway project from it.
2. Add a **PostgreSQL** database to the same project.
3. On the bot service → Variables:
   - `DISCORD_TOKEN` = your token
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (use the "Add reference" option, with your database's service name)
   - `THROWBACK_CHANNEL_ID` = the channel ID
   - optional: `THROWBACK_HOUR_UTC` (default 12), `BOT_PREFIX` (default `!`)
4. Start command: `python main.py` (the included `Procfile` says this too).
5. Look for `Logged in as ...` in the deploy logs, then run `!backfill` in your server.

`.python-version` pins Python 3.12 so every dependency has prebuilt wheels. If Railway complains about it, delete that file.

## Notes

- Voice sessions are timed in memory; they're saved when someone leaves voice or the bot shuts down cleanly. A hard crash loses sessions that were open at that moment.
- Message text is stored in your database so the throwback can pull from it. Command messages (starting with the prefix) and bot messages are not stored.
- Tests for the pure helpers: `python tests/test_helpers.py`.
