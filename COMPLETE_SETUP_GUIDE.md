# Complete Setup Guide 📚

Everything you need to set up, test, and deploy your Discord bot!

---

## 📋 Overview

This guide covers 3 main steps:
1. **Setup PostgreSQL** - Database for storing messages and activity
2. **Test Bot Locally** - Run bot on your computer to verify it works
3. **Deploy to Railway** - Put bot in production (24/7 hosting)

**Time required:** ~30 minutes total

---

## Part 1️⃣: PostgreSQL Setup (5-10 minutes)

Your bot needs a database. Choose one option:

### Option A: Simple SQLite (No Setup, Good for Testing)

```bash
# Just use this in your .env:
DATABASE_URL=sqlite:///discord_bot.db
```

Skip to Part 2! No installation needed.

### Option B: PostgreSQL Local (Better for Production Testing)

See **SETUP_POSTGRESQL.md** for complete instructions.

**Quick Start:**

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
psql
CREATE DATABASE discord_bot;
\q
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
psql
CREATE DATABASE discord_bot;
\q
```

**Windows:**
- Download from [postgresql.org](https://www.postgresql.org/download/windows/)
- Install (set password for postgres user)
- Open PowerShell as Admin:
  ```powershell
  psql -U postgres
  CREATE DATABASE discord_bot;
  \q
  ```

**Get Connection String:**
```
postgresql+asyncpg://postgres@localhost:5432/discord_bot
# OR with password:
postgresql+asyncpg://postgres:your_password@localhost:5432/discord_bot
```

---

## Part 2️⃣: Test Bot Locally (10-15 minutes)

See **SETUP_LOCAL_TESTING.md** for complete instructions.

### Quick Start:

**Step 1: Get Discord Bot Token**
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. New Application → Add Bot → Copy Token
3. OAuth2 → URL Generator → Select "bot" + permissions
4. Invite to your server

**Step 2: Create .env File**

```bash
cd discord-bot
cp .env.example .env
```

Edit `.env` with:
```
DISCORD_TOKEN=your_token_here
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/discord_bot
# OR for SQLite:
# DATABASE_URL=sqlite:///discord_bot.db
GUILD_ID=your_server_id
THROWBACK_CHANNEL_ID=your_channel_id
LOG_LEVEL=INFO
BOT_PREFIX=!
```

**Step 3: Install & Run**

**macOS/Linux:**
```bash
cd discord-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m bot.main
```

**Windows:**
```bash
cd discord-bot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m bot.main
```

**Or use scripts:**
```bash
./run.sh      # macOS/Linux
run.bat       # Windows
```

**Expected Output:**
```
Bot logged in as YourBotName#1234
Bot ID: 1234567890
Database initialized successfully
Cogs loaded
Commands synced with Discord
```

### Test in Discord:
```
!mystats              # Should show 1 message (your test)
!leaderboard          # Should show you ranked
!throwback_now        # Should post random message
```

✅ **Bot is working!**

---

## Part 3️⃣: Deploy to Railway (5-10 minutes)

See **SETUP_RAILWAY.md** for complete instructions.

### Quick Start:

**Step 1: Prepare Code**

Push code to GitHub:
```bash
cd discord-bot
git init
git add .
git commit -m "Discord bot"
git remote add origin https://github.com/YOUR_USERNAME/discord-bot.git
git push -u origin main
```

**Step 2: Create Railway Account**

1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Authorize connection

**Step 3: Deploy Bot**

1. Railway Dashboard → "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your discord-bot repo
4. Click "Deploy Now"

Wait for deployment to start (~1 minute).

**Step 4: Add PostgreSQL Database**

1. Click your project
2. Click "New" → "Database" → "PostgreSQL"
3. Wait for database to start (~30 seconds)

**Step 5: Set Environment Variables**

Get PostgreSQL connection string:
1. Click "PostgreSQL" service
2. Go to "Connect" tab
3. Copy connection string

Set variables on Bot service:
1. Click "Bot" service (or "web")
2. Go to "Variables" tab
3. Add:
   - `DISCORD_TOKEN` = your bot token
   - `DATABASE_URL` = PostgreSQL connection string
   - `GUILD_ID` = your server ID
   - `THROWBACK_CHANNEL_ID` = your channel ID
   - `LOG_LEVEL` = `INFO`
   - `BOT_PREFIX` = `!`

**Step 6: Set Startup Command**

1. Click "Bot" service
2. Go to "Settings" tab
3. Find "Start Command"
4. Set to: `python -m bot.main`
5. Save

**Step 7: Monitor**

1. Go to "Deployments" tab
2. Wait for ✅ Success
3. Go to "Logs" tab
4. Look for: "Bot logged in as..."

✅ **Bot is live!**

### Test in Discord:
```
!mystats              # Should work
!leaderboard          # Should show activity
```

---

## Summary: What You Now Have

| Component | Status | Location |
|-----------|--------|----------|
| **Bot Code** | ✅ Ready | discord-bot/ folder |
| **Database** | ✅ Running | PostgreSQL or SQLite |
| **Testing** | ✅ Done | Local machine |
| **Production** | ✅ Deployed | Railway.app |
| **Availability** | ✅ 24/7 | Railway hosts bot |

---

## Deployment Architecture

```
                Your Computer
                     ↓
              (Local Testing)
                     ↓
            GitHub Repository
                     ↓
                Railway.app
                     ↓
          ┌─────────────────────┐
          │                     │
          ↓                     ↓
    Bot Service            PostgreSQL
  (Runs your bot)      (Stores messages)
          ↓
    Discord Servers
    (Your bot active)
```

---

## Next Steps

After deployment:

1. **Monitor bot activity**
   - Check Railway logs daily
   - Verify bot appears online in Discord

2. **Customize fun responses**
   ```
   !addfunresponse sarcastic "Your response here"
   !addfunresponse meme "Your meme response"
   ```

3. **Adjust throwback time**
   ```
   !throwback_set 14 30    # 2:30 PM UTC
   ```

4. **Build leaderboards**
   - Users message in channels
   - Check `!leaderboard` to see rankings

5. **Scale when needed**
   - Upgrade Railway plan ($5+/month) for guaranteed uptime
   - Add more features to your bot

---

## Troubleshooting Quick Links

- **PostgreSQL Issues?** → See SETUP_POSTGRESQL.md → Troubleshooting
- **Local Testing Issues?** → See SETUP_LOCAL_TESTING.md → Troubleshooting
- **Railway Deployment Issues?** → See SETUP_RAILWAY.md → Troubleshooting
- **General Bot Issues?** → See README.md → Troubleshooting

---

## Command Cheat Sheet

### User Commands
```
!mystats                           # Show your stats
!leaderboard messages              # Top message senders
!leaderboard voice                 # Top voice participants
!leaderboard combined              # Top by engagement
!mystats_top3                       # Are you in top 3?
```

### Admin Commands
```
!throwback_now                     # Manually trigger throwback
!throwback_set HOUR MINUTE         # Set daily time
!addfunresponse CATEGORY TEXT      # Add custom response
!funresponses                       # List all responses
```

---

## File Reference

| File | Purpose |
|------|---------|
| QUICKSTART.md | 5-minute fast setup |
| SETUP_POSTGRESQL.md | Database installation |
| SETUP_LOCAL_TESTING.md | Local testing guide |
| SETUP_RAILWAY.md | Production deployment |
| COMPLETE_SETUP_GUIDE.md | This file (overview) |
| README.md | Full documentation |
| requirements.txt | Python dependencies |
| .env.example | Configuration template |
| run.sh / run.bat | Launch scripts |

---

## Support Resources

1. **Check Your Logs**
   - Local: `cat bot.log` or `type bot.log`
   - Railway: Dashboard → Logs tab

2. **Common Issues**
   - Missing .env values → Check SETUP_LOCAL_TESTING.md
   - Database connection → Check SETUP_POSTGRESQL.md
   - Railway deployment → Check SETUP_RAILWAY.md

3. **Need Help?**
   - Discord docs: https://discord.com/developers/docs
   - discord.py docs: https://discordpy.readthedocs.io
   - Railway docs: https://docs.railway.app
   - PostgreSQL docs: https://www.postgresql.org/docs

---

## You're All Set! 🎉

### What you have:
✅ Discord bot running locally
✅ Database storing activity
✅ Commands responding in Discord
✅ Bot deployed to production (Railway)
✅ 24/7 hosting included
✅ Free tier with 500 hours/month

### What's next:
1. Test all commands in your server
2. Invite friends to see activity tracking
3. Customize fun responses
4. Monitor bot performance
5. Scale up when ready

---

## Quick Reference Table

| Task | Time | Guide |
|------|------|-------|
| Set up database | 5-10 min | SETUP_POSTGRESQL.md |
| Test locally | 10-15 min | SETUP_LOCAL_TESTING.md |
| Deploy to Railway | 5-10 min | SETUP_RAILWAY.md |
| **Total** | **30 min** | **This guide** |

---

**Start with Part 1 (PostgreSQL) → Part 2 (Local Testing) → Part 3 (Railway)**

**Questions? Check the specific guide files above! ☝️**

**Your Discord bot is ready to launch! 🚀**
