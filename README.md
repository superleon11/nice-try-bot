# funbot

A small Discord bot: occasional fun replies, activity tracking (messages + voice time), `!mystats` / `!leaderboard`, and a daily "Throwback of the Day".

Only three dependencies: `discord.py`, `asyncpg`, `python-dotenv`. Tables are created automatically on first start.

## Commands

| Command | Who | What |
|---|---|---|
| `!mystats` | anyone | your messages, voice time and ranks |
| `!leaderboard [messages\|voice\|combined]` (`!lb`) | anyone | top 10 (combined = messages + voice minutes) |
| `!throwback` | Manage Server | dig up a throwback right now (takes a few minutes on a big server) |
| `!soundtest` | Manage Server | join your current voice channel now, play a soundboard clip, leave |
| `!note add @user text` | Manage Server | add a note about someone (also `!note list @user`, `!note edit <id> text`, `!note remove <id>`) |
| `!imagine <description>` | anyone | make an image (or just say "generate me an image of ...", see below) |
| `!learnnow` | Manage Server | turn what the bot has seen so far into notes right now (normally daily) |
| `!llmusage` | Manage Server | show AI spending against the caps |

Mentioning the bot always gets a reply. Keyword replies are limited to one per channel every 5 minutes, and fire about half the time.

## Throwback of the Day

The bot works with **one channel**, the one you set in `THROWBACK_CHANNEL_ID`. Once a day, at a **random time between 10am and 3pm UK time** (a different time each day), it picks a random window of history (30 to 60 days long) anywhere between when that channel was created and now, reads that slice of the channel's history straight from Discord, chooses a message, posts it in the same channel, and forgets everything it read. **No message history is stored in the database.** NSFW channels work fine.

**With the AI on** (`ANTHROPIC_API_KEY` set), the bot collects a pool of up to about 140 candidate messages from the window (the 40 most-reacted plus a random sample of the rest, so funny messages nobody reacted to still get a chance) and sends them, with their authors, to the model in a single call. The model picks the funniest or most interesting one, writes a one-line comment in the bot's voice (shown as "The bot's verdict"), and writes a prompt for a cartoon-style illustration. If `OPENAI_API_KEY` is set too, the bot generates that image and attaches it to the post. Those ~140 messages are sent to Anthropic for this one call and are not kept anywhere else.

**Fallbacks.** If the AI is off, hits the cost cap, errors, or gives an unusable answer, the bot picks randomly from the 10 most-reacted messages, as before. If only the image fails or is over budget, the post goes out with the text and comment but no image.

It skips bots, commands, link-only messages, very short or very long messages and `@everyone`/`@here` messages. **Redrawing.** Each window gets a random length (half to full `THROWBACK_WINDOW_DAYS`) and a random position, and never overlaps a window already tried. If a window has fewer than `THROWBACK_MIN_MESSAGES` (default 10) usable messages, the bot throws it away and draws another, up to `THROWBACK_MAX_ATTEMPTS` (default 40) times. If none reaches the minimum, it uses the best one it saw, as long as it had at least one usable message. Windows used on previous days are avoided too (this memory is lost when the bot restarts). Empty windows are quick to check, but a busy 60-day window means a lot of reading, so a run can take several minutes. Threads are not searched.

**Cost.** The judging call defaults to Claude Sonnet 5.5 (`LLM_THROWBACK_MODEL`), since judging humour is the point of it: roughly 10-20k input tokens, a few cents a day. Set it to `claude-haiku-4-5-20251001` to make it cheaper. The image is billed like any other (see Image generation). Both count toward the spending caps, and the image reserves `IMAGE_MAX_COST_USD` first, so make sure `LLM_DAILY_BUDGET_USD` leaves room.

The bot needs **View Channel**, **Read Message History**, **Send Messages** and **Attach Files** in that channel. `!throwback` always posts in the throwback channel, wherever you type it. The schedule is picked fresh after every restart; the bot checks the channel for today's throwback first, so a redeploy won't cause a second post that day. The next run time is printed in the deploy logs (`Next throwback at ...`).

Options: `THROWBACK_CHANNEL_ID`, `THROWBACK_START_HOUR` (default 10), `THROWBACK_END_HOUR` (default 15) and `THROWBACK_TIMEZONE` (default `Europe/London`; use any IANA name like `America/New_York`; summer time is handled for you), `THROWBACK_WINDOW_DAYS` (default 60), `THROWBACK_MIN_MESSAGES`, `THROWBACK_MAX_ATTEMPTS`, `THROWBACK_AI_PICK` (true/false), `THROWBACK_IMAGE` (true/false), `LLM_THROWBACK_MODEL`, and optionally `THROWBACK_SOURCE_CHANNEL_ID` to read history from a different channel than the one it posts in. For safety, the bot refuses to post if the channel it reads from is NSFW and the one it posts in isn't.

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

**Follow-ups without an @.** Replying to one of the bot's messages (Discord's reply button) always counts as talking to it. On top of that, after the bot replies to you, your next messages in that channel within 3 minutes (`LLM_CONVO_WINDOW_SECONDS=180`) count too, so you can just keep typing. Each exchange extends the window, and it only applies to you: other people still need an @ or a reply. It ignores a message that mentions someone else or replies to someone else's message. Set it to `0` to switch it off.

**Chiming in unprompted.** The bot also occasionally replies to messages that don't mention it. By default about 5% of messages (`LLM_RANDOM_REPLY_CHANCE=0.05`), with at least 5 minutes between chime-ins in a channel (`LLM_RANDOM_COOLDOWN_SECONDS=300`), in every channel it can see. To limit it to certain channels, set `LLM_RANDOM_CHANNEL_IDS` to a comma-separated list of channel IDs. The AI may decide it has nothing good to say and stay silent. Set the chance to `0` to switch this off. Over the cost cap, it falls back to the old canned keyword replies (so those only run when unprompted replies are off or the cap is hit). Each chime-in counts toward the spending cap like any other call.

The bot's personality is `LLM_PERSONA` (a default is built in). The AI's replies can never ping `@everyone` or roles.

## Image generation

Say something like **"generate me an image of a cat in a wizard hat"** (also "make / create / draw a picture of ...", with or without @ing the bot, as long as the message *starts* that way) or use `!imagine a cat in a wizard hat`, and the bot replies with the picture. Needs `OPENAI_API_KEY` (an OpenAI API key; API billing is separate from a ChatGPT subscription). Without it, nothing image-related runs. OpenAI says you may need to complete **Organization Verification** in the OpenAI developer console before GPT image models work for your account; if every request fails with an HTTP 403, that's why.

**Model.** `gpt-image-2.5-flare` by default (`IMAGE_MODEL` to change it, for example to `gpt-image-2.5-sunburst`). OpenAI bills it per token: $5 / 1M text input tokens and $30 / 1M image output tokens, so a medium 1024x1024 picture should cost a few cents. Quality (`IMAGE_QUALITY`: low, medium, high, xhigh, max, auto; default medium) and size (`IMAGE_SIZE`, default 1024x1024) are the main cost levers. OpenAI's content moderation still applies; if it refuses a prompt, the bot says it couldn't make that one.

**Cost cap.** The real cost is worked out from the token usage OpenAI reports and counts toward the same totals as the chat spend (`!llmusage`). OpenAI doesn't publish a fixed worst-case price per image, so before each image the bot reserves `IMAGE_MAX_COST_USD` (default $0.25) and refuses if that wouldn't fit under: `IMAGE_DAILY_BUDGET_USD` (images only, default $1.00), `LLM_DAILY_BUDGET_USD` and `LLM_MONTHLY_BUDGET_USD`. **The default overall daily cap of $0.50 only leaves room for a couple of images a day, so raise `LLM_DAILY_BUDGET_USD` (say to 2) if you want more.** Check the first few images on your OpenAI usage page to confirm the real cost, and lower `IMAGE_MAX_COST_USD` if it's well under 25 cents.

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
   - optional: `BOT_PREFIX` (default `!`)
4. Start command: `python main.py` (the included `Procfile` says this too).
5. Look for `Logged in as ...` in the deploy logs, then try `!throwback` in your server.

`.python-version` pins Python 3.12 so every dependency has prebuilt wheels. If Railway complains about it, delete that file.

## Notes

- Voice sessions are timed in memory; they're saved when someone leaves voice or the bot shuts down cleanly. A hard crash loses sessions that were open at that moment.
- The database holds per-user counters (message count and voice time), the notes about people, and AI spend. Message text is never stored.
- `!mystats` and `!leaderboard` only count activity from when the bot was added. They do not include old history.
- Tests: run each file in `tests/` with `python tests/<file>.py` (helpers, archive, soundboard_logic, llm, brain_logic, images, throwback_ai, throwback_cog, schedule).
