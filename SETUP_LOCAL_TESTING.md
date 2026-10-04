# Local Testing Guide 🧪

Step-by-step guide to test your Discord bot locally before deployment.

## Prerequisites

Before starting, you need:
1. ✅ Discord bot token (from Developer Portal)
2. ✅ PostgreSQL installed & running (see SETUP_POSTGRESQL.md)
3. ✅ Your server ID (right-click server → Copy ID)
4. ✅ A channel for throwback (right-click channel → Copy ID)

---

## Step 1: Get Discord Bot Token

### If you haven't already:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Name it: "Discord Fun Bot"
4. Go to "Bot" tab → "Add Bot"
5. Under TOKEN section, click "Copy"
6. **Save this token securely** (don't share it!)

### Enable Required Intents

Still in Developer Portal:
1. Go to "Bot" tab
2. Scroll down to "GATEWAY INTENTS"
3. Enable:
   - ✅ Message Content Intent (required to read messages)
   - ✅ Server Members Intent (optional, for member tracking)
   - ✅ Voice States Intent (for voice channel tracking)
4. Click "Save Changes"

### Invite Bot to Your Server

1. Go to "OAuth2" → "URL Generator"
2. Under SCOPES, select: `bot`
3. Under PERMISSIONS, select:
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Read Message History
   - ✅ Connect (voice)
   - ✅ Speak (voice)
4. Copy the URL at bottom
5. Paste URL in browser and select your server

**Bot is now in your server!** ✅

---

## Step 2: Create .env File

### Step 2a: Get Your IDs

**Get Server ID (GUILD_ID):**
1. Right-click your Discord server name
2. Click "Copy Server ID"

**Get Channel ID (THROWBACK_CHANNEL_ID):**
1. Create a channel like #bot-testing or #throwback
2. Right-click the channel
3. Click "Copy Channel ID"

### Step 2b: Edit .env

```bash
# Navigate to bot directory
cd discord-bot

# Copy template
cp .env.example .env

# Edit .env with your editor
# macOS/Linux
nano .env

# Windows
notepad .env
```

**Fill in these values:**

```
DISCORD_TOKEN=your_actual_bot_token_here
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/discord_bot
GUILD_ID=123456789
THROWBACK_CHANNEL_ID=987654321
LOG_LEVEL=INFO
BOT_PREFIX=!
```

**Save and exit** (Ctrl+X → Y → Enter for nano, Ctrl+S for notepad)

---

## Step 3: Install Dependencies

### macOS/Linux

```bash
# Navigate to bot directory
cd discord-bot

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Windows

```bash
# Navigate to bot directory
cd discord-bot

# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Wait for installation to complete** - should take 2-3 minutes.

---

## Step 4: Verify Database Connection

Before running the bot, test your database connection:

### macOS/Linux

```bash
# Make sure venv is activated
source venv/bin/activate

# Test connection
python3 << 'EOF'
import asyncpg
import asyncio

async def test():
    try:
        conn = await asyncpg.connect(
            user='postgres',
            database='discord_bot',
            host='localhost',
            port=5432
        )
        print("✅ Database connection successful!")
        await conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Make sure PostgreSQL is running!")

asyncio.run(test())
EOF
```

### Windows

```cmd
REM Make sure venv is activated
venv\Scripts\activate

REM Test connection
python << EOF
import asyncpg
import asyncio

async def test():
    try:
        conn = await asyncpg.connect(
            user='postgres',
            database='discord_bot',
            host='localhost',
            port=5432
        )
        print("✅ Database connection successful!")
        await conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Make sure PostgreSQL is running!")

asyncio.run(test())
EOF
```

**Expected output:**
```
✅ Database connection successful!
```

If you get an error, check Troubleshooting section below.

---

## Step 5: Start the Bot

### macOS/Linux (Using Script)

```bash
cd discord-bot
./run.sh
```

### Windows (Using Script)

```bash
cd discord-bot
run.bat
```

### Manual Start (Any OS)

```bash
# Make sure venv is activated
cd discord-bot

# macOS/Linux
source venv/bin/activate
python -m bot.main

# Windows
venv\Scripts\activate
python -m bot.main
```

**Expected output:**
```
Bot logged in as YourBotName#1234
Bot ID: 1234567890
Database initialized successfully
Loaded cog: bot.cogs.activity_tracking
Loaded cog: bot.cogs.fun_replies
Loaded cog: bot.cogs.stats_commands
Loaded cog: bot.cogs.throwback
Commands synced with Discord
```

**🎉 Bot is running!** Press `Ctrl+C` to stop.

---

## Step 6: Test in Discord

Now test your bot in your server!

### Test Activity Tracking

```
Send a message in a channel where the bot can see it
```

Then check that it was tracked:
```
!mystats
```

You should see an embed with your stats (1 message).

### Test Commands

Try these commands:

```
!mystats                    # See your stats
!leaderboard                # See rankings (should show your name)
!leaderboard voice          # Voice rankings (empty if no voice)
!mystats_top3               # Check if top 3
```

### Test Voice Tracking

```
1. Join a voice channel
2. Stay for 30 seconds
3. Leave the channel
4. Run: !mystats
5. You should see voice time added
```

### Test Fun Replies

Type messages with keywords to trigger responses:

```
"that's really nice"    → Might get wholesome reply
"wow nice idea"         → Might get sarcastic reply
"that's fire"           → Might get meme reply
```

Note: Only 30% chance to respond when keywords are found. Send multiple messages!

### Test Throwback

```
!throwback_now          # Manually trigger (admin only)
```

A random old message should appear in your throwback channel.

---

## Monitoring & Logs

### View Real-time Logs

**In terminal:**
The bot prints all logs while running - watch for messages, errors, voice events, etc.

### Check Log File

```bash
# View bot logs
cat bot.log

# macOS/Linux - follow in real-time
tail -f bot.log
```

### Expected Log Examples

```
2026-10-04 15:30:00 - bot.cogs.activity_tracking - DEBUG - Tracked message: jordan in Test Server
2026-10-04 15:30:15 - bot.cogs.activity_tracking - DEBUG - jordan joined voice channel in Test Server
2026-10-04 15:30:45 - bot.cogs.activity_tracking - DEBUG - jordan left voice channel after 0h 0m
2026-10-04 15:31:00 - bot.cogs.fun_replies - DEBUG - Replied to message in Test Server
```

---

## Troubleshooting

### Bot Not Responding

**Problem:** Bot in server but not responding to commands

**Solutions:**
1. Check bot has "Send Messages" permission
   - Right-click server → Server Settings → Roles
   - Find your bot role → Permissions → Enable "Send Messages"

2. Verify MESSAGE_CONTENT intent is enabled
   - Developer Portal → Application → Bot → Enable "Message Content Intent"

3. Check bot is online
   - Look in member list - bot should show as online

4. Check for errors in terminal output

### "Connection refused" on startup

**Problem:** Can't connect to PostgreSQL

**Solutions:**
```bash
# Check PostgreSQL is running
# macOS
brew services list | grep postgresql

# Linux
sudo systemctl status postgresql

# Windows - Services app (search "Services")
# Find PostgreSQL and click Start

# Start PostgreSQL if not running
# macOS
brew services start postgresql@15

# Linux
sudo systemctl start postgresql
```

### "Invalid Discord token"

**Problem:** Wrong or expired token

**Solutions:**
1. Get new token from Developer Portal
2. Make sure you copied the full token (very long string)
3. Make sure no spaces at start/end
4. Paste into .env without quotes

### "GUILD_ID not set"

**Problem:** Missing guild ID in .env

**Solutions:**
1. Right-click Discord server name
2. Click "Copy Server ID"
3. Paste into `.env` as `GUILD_ID=123456789`

### "THROWBACK_CHANNEL_ID not set"

**Problem:** Missing channel ID in .env

**Solutions:**
1. Create channel for throwback
2. Right-click channel
3. Click "Copy Channel ID"
4. Paste into `.env` as `THROWBACK_CHANNEL_ID=987654321`

### Bot responds but commands don't work

**Problem:** Commands not synced

**Solutions:**
1. Bot syncs commands on startup - wait 30 seconds
2. Refresh Discord (Ctrl+R)
3. Try typing command slowly
4. Check bot has administrator permission (temporary, for testing)

### "ModuleNotFoundError"

**Problem:** Missing dependencies

**Solutions:**
```bash
# Make sure venv is activated
# macOS/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

# Reinstall requirements
pip install -r requirements.txt
```

### No activity being tracked

**Problem:** Messages/voice not being recorded

**Solutions:**
1. Check bot has "Read Messages" permission
2. Check bot has "Connect" and "Speak" permissions
3. Check DATABASE_URL is correct in .env
4. Test database connection (Step 4 above)
5. Check bot.log for database errors

---

## Stopping the Bot

```bash
# In terminal where bot is running
Ctrl+C

# Or close terminal
```

The bot will disconnect from Discord gracefully.

---

## Next Steps

Once bot is working locally:

1. **Test all features thoroughly**
   - Messages, voice, commands, throwback

2. **Customize fun responses**
   - Add more keywords and responses

3. **Set throwback time**
   ```
   !throwback_set 14 30  # 2:30 PM UTC (adjust for your timezone)
   ```

4. **Deploy to production**
   - See SETUP_RAILWAY.md for Railway deployment

---

## Common Testing Scenarios

### Scenario 1: Test Message Tracking
1. Send message: "hello world"
2. Run: `!mystats`
3. Should see 1 message

### Scenario 2: Test Voice Tracking
1. Join voice channel
2. Wait 1 minute
3. Leave voice channel
4. Run: `!mystats`
5. Should see 1+ minutes in voice time

### Scenario 3: Test Leaderboard
1. Message multiple times (get 10+ messages)
2. Invite another user
3. Have them message too
4. Run: `!leaderboard messages`
5. Should see both users ranked

### Scenario 4: Test Fun Replies
1. Type: "wow that's really nice"
2. Wait (bot might not always respond)
3. Repeat message a few times
4. Bot should reply occasionally

### Scenario 5: Test Admin Commands
1. Run: `!throwback_now`
2. Random message appears in throwback channel
3. Success! ✅

---

**You're ready to test! 🚀**

Run `./run.sh` or `run.bat` and try it out in your server!

Need help? Check Troubleshooting section above. 👆
