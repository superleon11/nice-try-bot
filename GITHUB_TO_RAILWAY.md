# GitHub to Railway: Complete Deployment Guide 🚀

Push your bot to GitHub and deploy it to Railway in just a few minutes!

---

## Quick Overview

```
Local Code → GitHub → Railway → 24/7 Bot
```

---

## Step 1: Create GitHub Account & Repository

### 1a. Create GitHub Account (if needed)

1. Go to [github.com](https://github.com)
2. Click "Sign up"
3. Complete registration
4. ✅ You have a GitHub account!

### 1b. Create New Repository

1. Go to [github.com/new](https://github.com/new)
2. Name it: `discord-bot`
3. Description: `Discord bot with activity tracking, fun replies, and daily throwback`
4. Set to **Public** (required for Railway free tier)
5. Click "Create repository"
6. ✅ You have an empty repo!

**Copy your repository URL:**
```
https://github.com/YOUR_USERNAME/discord-bot.git
```

You'll need this in the next step!

---

## Step 2: Push Bot Code to GitHub

### Option A: Automatic Script (Easiest)

**macOS/Linux:**
```bash
cd /home/claude/discord-bot
chmod +x push_to_github.sh
./push_to_github.sh https://github.com/YOUR_USERNAME/discord-bot.git
```

**Windows:**
```bash
cd discord-bot
push_to_github.bat https://github.com/YOUR_USERNAME/discord-bot.git
```

The script will:
1. Initialize git
2. Add all files
3. Create a commit
4. Push to GitHub
5. ✅ Done! Your code is on GitHub!

**You may be asked to authenticate - just follow the prompts.**

### Option B: Manual Steps

If you prefer manual control, see **SETUP_GITHUB.md**.

---

## Step 3: Verify on GitHub

1. Go to `https://github.com/YOUR_USERNAME/discord-bot`
2. You should see:
   - ✅ bot/ folder
   - ✅ database/ folder
   - ✅ requirements.txt
   - ✅ All setup guides
3. Everything looks good!

---

## Step 4: Deploy to Railway

### 4a. Create Railway Account

1. Go to [railway.app](https://railway.app)
2. Click "Sign in with GitHub"
3. Authorize Railway
4. ✅ You have a Railway account!

### 4b. Deploy Your Bot

1. Go to [railway.app/dashboard](https://railway.app/dashboard)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Select your GitHub account
5. Find and select `discord-bot` repo
6. Click "Deploy Now"

Railway will:
- Clone your repo
- Detect Python
- Create a service
- Start building (~2 minutes)

### 4c. Add PostgreSQL Database

While bot is deploying:

1. Click your project name
2. Click "New" button (top right)
3. Select "Database" → "PostgreSQL"
4. Wait for database to start (~30 seconds)

✅ PostgreSQL is ready!

### 4d. Set Environment Variables

Get PostgreSQL connection string:
1. Click "PostgreSQL" service
2. Go to "Connect" tab
3. Copy the connection string

Set bot variables:
1. Click "Bot" service (or "web")
2. Go to "Variables" tab
3. Add these variables:

```
DISCORD_TOKEN = your_bot_token_here
DATABASE_URL = postgresql+asyncpg://postgres:password@host:port/railway
GUILD_ID = your_server_id
THROWBACK_CHANNEL_ID = your_channel_id
LOG_LEVEL = INFO
BOT_PREFIX = !
```

### 4e. Set Startup Command

1. Click "Bot" service
2. Go to "Settings" tab
3. Find "Start Command"
4. Set to: `python -m bot.main`
5. Save

### 4f: Monitor Deployment

1. Go to "Deployments" tab
2. Watch for ✅ "Success"
3. Go to "Logs" tab
4. Look for: "Bot logged in as YourBotName#1234"

✅ Your bot is live!

---

## Step 5: Test in Discord

```
!mystats              # Should work
!leaderboard          # Should show your activity
!throwback_now        # Should post random message
```

✅ **Your bot is deployed and working!**

---

## What Happens Now?

### Auto-Deploy on GitHub Push

1. Make changes to code locally
2. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Your changes"
   git push origin main
   ```
3. Railway automatically deploys (~2 minutes)
4. Bot updates without downtime!

### Monitoring

- **Railway Dashboard** - Check logs, monitor CPU/memory
- **Discord** - Bot appears online automatically
- **Commands** - All features work immediately

### Scaling

When you hit 500 hours/month on free tier:
1. Go to Railway billing
2. Add payment method
3. Upgrade to paid ($5+/month)
4. Bot continues running 24/7!

---

## Troubleshooting

### "Authentication failed" when pushing to GitHub

1. You need to authenticate with GitHub
2. Git will prompt for username/password
3. For password, use a Personal Access Token:
   - Go to [github.com/settings/tokens](https://github.com/settings/tokens)
   - Generate new token
   - Select "repo" scope
   - Copy token and paste when prompted

### "Repository not found" when deploying on Railway

1. Make sure repository is **Public**
2. Go to GitHub repo settings
3. Change to "Public" visibility
4. Try Railway deployment again

### Bot service shows "Crashed"

1. Check "Logs" tab for error
2. Common issues:
   - Wrong DATABASE_URL
   - Missing environment variables
   - Invalid DISCORD_TOKEN
3. Fix and Railway redeploys automatically

### "Connection refused" in logs

1. PostgreSQL not ready yet (wait 1 minute)
2. Or DATABASE_URL is wrong
3. Check connection string in "PostgreSQL" → "Connect"
4. Update DATABASE_URL variable

---

## Complete Setup Checklist

- [ ] Create GitHub account
- [ ] Create GitHub repository
- [ ] Push bot code to GitHub
- [ ] Verify files on GitHub
- [ ] Create Railway account
- [ ] Deploy bot from GitHub
- [ ] Add PostgreSQL database
- [ ] Set environment variables
- [ ] Set startup command
- [ ] Check deployment status
- [ ] Test commands in Discord
- [ ] Bot is live! 🎉

---

## Quick Reference

| Step | Time | Command |
|------|------|---------|
| GitHub setup | 2 min | Go to github.com |
| Push code | 2 min | `./push_to_github.sh URL` |
| Railway setup | 3 min | Create project |
| Add database | 1 min | Click "New" → PostgreSQL |
| Configure vars | 2 min | Add environment variables |
| Test | 1 min | Run `!mystats` in Discord |
| **Total** | **11 min** | **Bot is live!** |

---

## Next Steps

### Immediately After Deployment
1. Test all commands in Discord
2. Check Railway logs
3. Invite friends to your server

### Within a Week
1. Monitor bot performance
2. Add custom fun responses
3. Adjust throwback time
4. Build activity leaderboards

### When Ready to Scale
1. Upgrade Railway plan ($5+/month)
2. Add more features
3. Invite more servers
4. Build dashboard (optional)

---

## Support Resources

- **Railway Docs**: https://docs.railway.app
- **Discord.py Docs**: https://discordpy.readthedocs.io
- **GitHub Docs**: https://docs.github.com
- **This Project**: See README.md

---

## Your New Workflow

```
1. Make changes locally
   ↓
2. Test with: python -m bot.main
   ↓
3. Commit: git commit -m "message"
   ↓
4. Push: git push origin main
   ↓
5. Railway deploys automatically
   ↓
6. Bot updates in Discord 🚀
```

---

## Estimated Costs

| Item | Cost | Notes |
|------|------|-------|
| GitHub | Free | Unlimited public repos |
| Railway Bot | Free | 500 hours/month (~21 days) |
| Railway PostgreSQL | Free | 5GB included |
| **Total** | **Free!** | Upgrade to paid ($5+) for unlimited |

---

**You're ready to deploy! 🚀**

**Next Steps:**
1. Follow this guide to push to GitHub
2. Deploy on Railway
3. Test in Discord
4. Your bot is live 24/7!

**Questions? Check the troubleshooting section above! ☝️**
