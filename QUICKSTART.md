# Quick Start Guide 🚀

Get your Discord bot up and running in 5 minutes!

## Step 1: Clone the Bot Repository

You already have the bot code! It's in `/home/claude/discord-bot/`

## Step 2: Create Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" → Name it "Discord Fun Bot"
3. Go to "Bot" tab → Click "Add Bot"
4. Under TOKEN, click "Copy" (save this for later!)
5. Go to "OAuth2" → "URL Generator"
6. Under SCOPES, select: `bot`
7. Under PERMISSIONS, select:
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Read Message History
   - ✅ Connect (voice)
   - ✅ Speak (voice)
8. Copy the generated URL and open it in your browser to invite bot to your server

## Step 3: Set Up .env File

### Mac/Linux:
```bash
cd discord-bot
cp .env.example .env
nano .env  # Edit the file
```

### Windows:
```bash
cd discord-bot
copy .env.example .env
notepad .env  # Edit the file
```

### What to Fill In:

**DISCORD_TOKEN** - Paste your bot token from Step 2

**DATABASE_URL** - Choose one:

**Option A: Quick Start (SQLite - Easiest)**
```
sqlite:///discord_bot.db
```

**Option B: PostgreSQL (Recommended for scale)**
```
postgresql+asyncpg://username:password@localhost:5432/discord_bot
```

**GUILD_ID** - Your Discord server ID (right-click server → Copy ID)

**THROWBACK_CHANNEL_ID** - Channel for daily throwback (right-click channel → Copy ID)

Example `.env`:
```
DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
DATABASE_URL=sqlite:///discord_bot.db
GUILD_ID=123456789
THROWBACK_CHANNEL_ID=987654321
LOG_LEVEL=INFO
BOT_PREFIX=!
```

## Step 4: Install Dependencies

### Mac/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Windows:
```bash
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Step 5: Run the Bot!

### Mac/Linux:
```bash
./run.sh
```

### Windows:
```bash
run.bat
```

### Or Manually:
```bash
python -m bot.main
```

You should see:
```
Bot logged in as YourBotName#1234
Bot ID: 123456789
Commands synced with Discord
```

🎉 **Your bot is now running!**

## Test Commands in Discord

Try these in your server:

```
!mystats              # See your activity stats
!leaderboard          # See message leaderboard
!leaderboard voice    # See voice time leaderboard
!throwback_now        # Manually trigger throwback (admin only)
```

## Troubleshooting

### "DISCORD_TOKEN not set in .env"
- Make sure `.env` file exists in the `discord-bot` folder
- Make sure DISCORD_TOKEN is set with your actual bot token

### "Bot not responding to commands"
- Make sure bot has Message permissions in your server
- Make sure bot is invited to the server
- Enable MESSAGE_CONTENT intent: Developer Portal → Application → Bot → Scroll to "MESSAGE_CONTENT INTENT" → Turn ON

### "Cannot connect to database"
- For SQLite: Make sure you have write permissions in the bot folder
- For PostgreSQL: Make sure PostgreSQL is running and connection string is correct

### "Bot offline"
- Check the console for error messages
- Look at `bot.log` file for detailed errors

## Next Steps

1. **Customize Fun Responses**
   - Edit response keywords in database
   - Use `!addfunresponse` command

2. **Adjust Throwback Time**
   - Use `!throwback_set 2 0` to set time (2:00 AM UTC)

3. **Monitor Activity**
   - Use `!leaderboard` to see activity rankings
   - Check `!mystats` for personal stats

4. **Deploy to Production**
   - Set up Railway account for free hosting
   - See README.md for deployment instructions

## Commands Cheat Sheet

### User Commands
- `!mystats` - Your activity stats
- `!leaderboard [messages|voice|combined]` - Server rankings
- `!mystats_top3` - Check if you're in top 3

### Admin Commands
- `!throwback_now` - Manually trigger throwback
- `!throwback_set HOUR MINUTE` - Set daily time
- `!addfunresponse CATEGORY TEXT` - Add custom response

## File Structure

```
discord-bot/
├── run.sh / run.bat       ← Use this to start the bot
├── .env                   ← Your configuration (create this)
├── bot/
│   ├── main.py           ← Bot startup code
│   └── cogs/             ← Features (replies, tracking, etc.)
├── database/
│   └── models.py         ← Database structure
└── requirements.txt      ← Python dependencies
```

## Getting Help

1. Check `bot.log` file for error messages
2. Review README.md for full documentation
3. Verify all `.env` values are correct
4. Make sure bot has proper Discord permissions

---

**That's it! Your Discord bot is ready to go! 🎉**

Have fun with your new bot! 🤖
