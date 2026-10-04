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
| `!note add @user text` | Manage Server | add a note about someone (also `!note list @user`, `!note edit <id> text`, `!note remove <id>`) |
| `!learnnow` | Manage Server | turn what the bot has seen so far into notes right now (normally daily) |
| `!llmusage` | Manage Server | show AI spending against the caps |

Mentioning the bot always gets a reply. Keyword replies are limited to one per channel every 5 minutes, and fire about half the time.

## Throwback of the Day

The bot works with **one channel**, the one you set in `THROWBACK_CHANNEL_ID`. Once a day it picks a random 30-day window between when that channel was created and now, reads that slice of the channel's history straight from Discord, picks one of the best messages in it, posts it in the same channel, and forgets everything it read. **No message history is stored in the database.** NSFW channels work fine.

"Best" means most reactions, with a small bonus for length and some randomness. It skips bots, commands, link-only messages, very short or very long messages and `@everyone`/`@here` messages, and then picks randomly from the top 10 so you don't always get the same message. If a window is empty or quiet (early years, say), it tries another window, up to 6 times. Threads are not searched.

The bot needs **View Channel**, **Read Message History** and **Send Messages** in that channel. `!throwback` always posts in the throwback channel, wherever you type it.

Options: `THROWBACK_CHANNEL_ID`, `THROWBACK_HOUR_UTC`, `THROWBACK_WINDOW_DAYS` (default 30), and optionally `THROWBACK_SOURCE_CHANNEL_ID` to read history from a different channel than the one it posts in. For safety, the bot refuses to post if the channel it reads from is NSFW and the one it posts in isn't.

## AI chat and memory

Set `ANTHROPIC_API_KEY` and the bot answers anyone who mentions it (or replies to one of its messages) with an AI-written reply, using whatever notes it has about the people involved. Without a key, none of this runs and the bot behaves as before. Create a key in the Anthropic developer console. API billing is separate from a claude.ai subscription.

**Models.** Both jobs default to Claude Haiku 4.5, the cheapest current model ($1 / $5 per million input / output tokens). For funnier chat replies, set `LLM_CHAT_MODEL=claude-sonnet-5-5` (about twice the price). Anything else the bot doesn't recognise is treated as the most expensive model for the cap, so it stays safe.

**Cost cap (the only limit).** Before every call the bot checks that even the worst case still fits under `LLM_DAILY_BUDGET_USD` (default 0.50) and `LLM_MONTHLY_BUDGET_USD` (default 10). Over the cap it quietly falls back to its normal canned replies, and notes learning waits until the budget is back. `!llmusage` shows where you are. As a second layer you can also set a spending limit on your account in the Anthropic console.

**Notes about people.** They live in the `user_notes` table. `source = 'manual'` notes are yours: the AI never edits or removes them. `source = 'auto'` notes are written by the AI, which may tidy them up (at most 30 per person are kept). Set them up with `!note add @user text`, or directly in the database (Railway → your Postgres → Data), for example:

```sql
-- see everyone's notes (user_id and guild_id are Discord IDs)
SELECT id, username, source, note FROM user_notes ORDER BY user_id, id;
-- add a base note (source defaults to 'manual')
INSERT INTO user_notes (guild_id, user_id, username, note) VALUES (123456789, 987654321, 'Dave', 'Always late to calls');
-- edit or delete
UPDATE user_notes SET note = 'Never on time, ever', source = 'manual' WHERE id = 12;
DELETE FROM user_notes WHERE id = 12;
```

**How it learns.** By default the bot only listens to messages addressed to it (mentions and replies). Set `LLM_LEARN_SCOPE=all` and it listens to everything said in the server, which gives richer notes but costs more. Messages are kept in memory only, and once a day (`LLM_MEMORY_HOUR_UTC`, default 04:00 UTC) the model turns them into short notes and they are discarded. Anyone with fewer than 3 messages is kept for the next day. A redeploy or restart loses whatever is still waiting. Use `!learnnow` to run it on demand.

The bot's personality is `LLM_PERSONA` (a default is built in). The AI's replies can never ping `@everyone` or roles.

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
- The database holds per-user counters (message count and voice time), the notes about people, and AI spend. Message text is never stored.
- `!mystats` and `!leaderboard` only count activity from when the bot was added. They do not include old history.
- Tests: run each file in `tests/` with `python tests/<file>.py` (helpers, archive, soundboard_logic, llm, brain_logic).
