# funbot

A small Discord bot: occasional fun replies, activity tracking (messages + voice time), `!mystats` / `!leaderboard`, and a daily "Throwback of the Day".

Only three dependencies: `discord.py`, `asyncpg`, `python-dotenv`. Tables are created automatically on first start.

## Commands

| Command | Who | What |
|---|---|---|
| `!mystats` | anyone | your messages, voice time and ranks |
| `!leaderboard [messages\|voice\|combined]` (`!lb`) | anyone | top 10 (combined = messages + voice minutes) |
| `!throwback` | Manage Server | dig up a throwback right now (takes a minute or two on a big server) |
| `!soundtest` | Manage Server | join your current voice channel now, play a soundboard clip, leave |

Mentioning the bot always gets a reply. Keyword replies are limited to one per channel every 5 minutes, and fire about half the time.

## Throwback of the Day

The bot works with **one channel**, the one you set in `THROWBACK_CHANNEL_ID`. Once a day it picks a random 30-day window between when that channel was created and now, reads that slice of the channel's history straight from Discord, picks one of the best messages in it, posts it in the same channel, and forgets everything it read. **No message history is stored in the database.** NSFW channels work fine.

"Best" means most reactions, with a small bonus for length and some randomness. It skips bots, commands, link-only messages, very short or very long messages and `@everyone`/`@here` messages, and then picks randomly from the top 10 so you don't always get the same message. If a window is empty or quiet (early years, say), it tries another window, up to 6 times. Threads are not searched.

The bot needs **View Channel**, **Read Message History** and **Send Messages** in that channel. `!throwback` always posts in the throwback channel, wherever you type it.

Options: `THROWBACK_CHANNEL_ID`, `THROWBACK_HOUR_UTC`, `THROWBACK_WINDOW_DAYS` (default 30), and optionally `THROWBACK_SOURCE_CHANNEL_ID` to read history from a different channel than the one it posts in. For safety, the bot refuses to post if the channel it reads from is NSFW and the one it posts in isn't.

## Soundboard visits

Once a voice call has had at least 2 people in it for 15 minutes, the bot waits a random 15-45 minutes, joins, plays one random soundboard clip, and leaves. If the call is still going it comes back again after another random 15-45 minutes. If the call drops below 2 people, the timers reset. It picks from your server's own soundboard, or Discord's default sounds if the server has none.

Everything is adjustable with optional Railway variables (see `.env.example`): `SOUND_VISITS_ENABLED`, `SOUND_MIN_CALL_MINUTES`, `SOUND_MIN_DELAY_MINUTES`, `SOUND_MAX_DELAY_MINUTES`, `SOUND_MIN_HUMANS`.

The bot needs the **Connect**, **Speak** and **Use Soundboard** permissions in the voice channel. Easiest: Server Settings → Roles → the bot's role → enable those three. Or re-invite with this link (replace `YOUR_APP_ID`):
`https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot&permissions=4398049741824`

Joining voice needs the `discord.py[voice]` extra (already in `requirements.txt`; it installs PyNaCl and davey). Test it with `!soundtest` while you're in a voice channel.

## 1. Discord setup

1. https://discord.com/developers/applications → New Application → **Bot** tab → copy the token.
2. On the same tab enable **Message Content Intent** (the bot will not start without it).
3. **OAuth2 → URL Generator**: scope `bot`; permissions: View Channels, Send Messages, Read Message History, Embed Links, Connect, Speak, Use Soundboard. Open the URL to invite the bot.
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
5. Look for `Logged in as ...` in the deploy logs, then try `!throwback` in your server.

`.python-version` pins Python 3.12 so every dependency has prebuilt wheels. If Railway complains about it, delete that file.

## Notes

- Voice sessions are timed in memory; they're saved when someone leaves voice or the bot shuts down cleanly. A hard crash loses sessions that were open at that moment.
- The database only holds per-user counters (message count and voice time). Message text is never stored.
- `!mystats` and `!leaderboard` only count activity from when the bot was added. They do not include old history.
- Tests: `python tests/test_helpers.py`, `python tests/test_archive.py` and `python tests/test_soundboard_logic.py`.
