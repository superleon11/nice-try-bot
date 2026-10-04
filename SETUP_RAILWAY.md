# Railway Deployment Guide 🚀

Deploy your Discord bot to Railway for free! Railway includes PostgreSQL and 24/7 hosting.

## Why Railway?

✅ **Free tier** - 500 hours/month (~21 days continuous)
✅ **PostgreSQL included** - No extra database service to set up
✅ **Automatic restarts** - Bot stays online 24/7
✅ **Easy scaling** - Upgrade to paid ($5+/month) when ready
✅ **GitHub integration** - Deploy from your repo automatically
✅ **Environment variables** - Secure token storage
✅ **Logging** - Monitor bot activity in dashboard

---

## Step 1: Create Railway Account

1. Go to [railway.app](https://railway.app)
2. Click "Sign in with GitHub" (easiest)
   - OR sign up with email
3. Complete signup
4. Verify email if needed

**You now have a free Railway account! ✅**

---

## Step 2: Prepare Your Bot Code

### Push to GitHub (Recommended)

If your code isn't on GitHub yet, push it:

```bash
# Initialize git (if not already)
cd discord-bot
git init

# Add all files
git add .

# Create commit
git commit -m "Discord bot initial commit"

# Create repository on GitHub.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/discord-bot.git
git branch -M main
git push -u origin main
```

---

## Step 3: Create Railway Project

### Option A: From GitHub (Recommended)

1. Go to [railway.app/dashboard](https://railway.app/dashboard)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Connect your GitHub account (if not already)
5. Select `discord-bot` repository
6. Click "Deploy Now"

### Option B: Deploy from Repo Link

1. Go to [railway.app/dashboard](https://railway.app/dashboard)
2. Click "New Project"
3. Select "GitHub Repo"
4. Paste: `https://github.com/YOUR_USERNAME/discord-bot`
5. Click "Deploy"

Railway will automatically:
- Clone your repo
- Detect Python project
- Create a service
- Start deploying!

---

## Step 4: Add PostgreSQL Database

While deployment is running:

1. In Railway dashboard, click your project
2. Click "New" button (top right)
3. Select "Database" → "PostgreSQL"
4. Wait for PostgreSQL to provision (~30 seconds)

**PostgreSQL is now ready!** ✅

---

## Step 5: Configure Environment Variables

### Get PostgreSQL Connection String

1. In Railway dashboard, click "PostgreSQL" service
2. Go to "Connect" tab
3. Copy the connection string (looks like `postgresql://...`)

### Set Environment Variables

1. Click your "Bot" service (or "web" service)
2. Go to "Variables" tab
3. Add these variables:

**DISCORD_TOKEN**
- Value: Your bot token from Discord Developer Portal
- Click "Add variable"

**DATABASE_URL**
- Value: The PostgreSQL connection string you copied
- Make sure it starts with `postgresql+asyncpg://`
- Click "Add variable"

**GUILD_ID**
- Value: Your server ID
- Click "Add variable"

**THROWBACK_CHANNEL_ID**
- Value: Your channel ID for throwback
- Click "Add variable"

**LOG_LEVEL**
- Value: `INFO`
- Click "Add variable"

**BOT_PREFIX**
- Value: `!`
- Click "Add variable"

### Example Variables Screen

```
DISCORD_TOKEN = XXXXXXXXXXXXXXXXXXXX
DATABASE_URL = postgresql+asyncpg://postgres:password@host:port/railway
GUILD_ID = 123456789
THROWBACK_CHANNEL_ID = 987654321
LOG_LEVEL = INFO
BOT_PREFIX = !
```

---

## Step 6: Configure Startup Command

1. Click your "Bot" service
2. Go to "Settings" tab
3. Scroll to "Start Command"
4. Set to: `python -m bot.main`
5. Save

**Railway will automatically start your bot with this command! ✅**

---

## Step 7: Monitor Deployment

### Check Deployment Status

1. Go to "Deployments" tab
2. Watch the build progress
3. Once complete, status should be "✅ Success"

### View Logs

1. Go to "Logs" tab
2. Scroll through logs to see:
   ```
   Bot logged in as YourBotName#1234
   Database initialized successfully
   Cogs loaded
   Commands synced with Discord
   ```

### If Deployment Fails

Check logs for error messages:
- `ModuleNotFoundError` - Missing dependency (check requirements.txt)
- `Connection refused` - Database not ready (wait 1 minute)
- `Invalid token` - Wrong DISCORD_TOKEN value

Fix the issue, commit to GitHub, and Railway will redeploy automatically!

---

## Step 8: Verify Bot Is Running

### In Discord

1. Check if bot appears online in your server
2. Run a command: `!mystats`
3. Bot should respond

### In Railway Dashboard

1. Click your project
2. Click "Bot" service
3. Status should show "Running"
4. Memory usage should be stable (~100-200 MB)

**Your bot is live! 🎉**

---

## Setting Up Auto-Deploys

Railway automatically redeploys when you push to GitHub:

1. Make changes locally
2. Commit and push to GitHub
   ```bash
   git add .
   git commit -m "Update bot features"
   git push origin main
   ```
3. Railway automatically deploys (takes ~2 minutes)
4. Bot updates without downtime!

---

## Common Railway Issues & Solutions

### Bot Service Shows "Crashed"

**Problem:** Bot crashed and won't restart

**Solutions:**
1. Check "Logs" tab for error message
2. Fix the error in code
3. Push to GitHub (Railway redeploys)
4. Watch logs until "Bot logged in..."

### "Connection refused" in logs

**Problem:** Can't connect to PostgreSQL

**Solutions:**
1. Verify DATABASE_URL is correct in Variables
2. Make sure PostgreSQL service is running (check Dashboard)
3. Wait 1 minute for database to fully start
4. Restart bot service (click ⟳ button)

### "Invalid token" error

**Problem:** Wrong DISCORD_TOKEN

**Solutions:**
1. Get fresh token from Developer Portal
2. Update DISCORD_TOKEN variable in Railway
3. Railway automatically restarts bot

### Bot offline but no errors in logs

**Problem:** Service crashed silently

**Solutions:**
1. Click ⟳ (restart button) on bot service
2. Watch logs for startup message
3. If keeps crashing, check error in logs

### Database memory full

**Problem:** PostgreSQL out of storage (free tier limit)

**Solutions:**
1. Upgrade PostgreSQL plan (+$5/month)
2. Or delete old messages from database (advanced)

---

## Upgrading from Free to Paid

When your 500 hours/month runs out:

1. Go to [railway.app/account/billing](https://railway.app/account/billing)
2. Add payment method
3. Click "Upgrade" on your project
4. Choose plan:
   - **Starter** - $5/month (recommended)
   - **Pro** - $20/month
   - **Custom** - Variable pricing

**Your bot continues running 24/7 on paid tier! ✅**

---

## Monitoring Bot Activity

### View Logs Live

1. Dashboard → Click project
2. "Logs" tab
3. Scroll to see real-time bot activity

### Check Resource Usage

1. Dashboard → Click project
2. Watch "Memory" and "CPU" usage
3. Should be stable around 100-200 MB

### View Deployments

1. Dashboard → "Deployments" tab
2. See all past deployments
3. Click one to view logs from that deployment

---

## Advanced: Custom Domain (Optional)

If you want a custom URL for your bot dashboard:

1. Go to "Settings" tab
2. Scroll to "Domains"
3. Add custom domain
4. Configure DNS at your domain provider

---

## Troubleshooting Checklist

Before asking for help:

- [ ] Bot appears online in Discord
- [ ] DATABASE_URL set in Railway Variables
- [ ] DISCORD_TOKEN set in Railway Variables
- [ ] GUILD_ID and THROWBACK_CHANNEL_ID set
- [ ] Bot service status is "Running"
- [ ] No errors in Logs tab
- [ ] PostgreSQL service is "Running"
- [ ] Command: `!mystats` works in Discord

---

## Next Steps After Deployment

1. **Test all features in your server**
   ```
   !mystats
   !leaderboard
   !throwback_now
   ```

2. **Monitor bot performance**
   - Check Railway logs daily
   - Watch for errors or crashes

3. **Set up GitHub auto-deploys**
   - Make changes locally
   - Push to GitHub
   - Railway deploys automatically

4. **Scale up when needed**
   - Upgrade Railway plan for 24/7 guaranteed uptime
   - Add more features to your bot

---

## Useful Railway Links

- **Dashboard**: https://railway.app/dashboard
- **Billing**: https://railway.app/account/billing
- **Docs**: https://docs.railway.app
- **Support**: https://railway.app/support

---

## Quick Reference

**Deployment Summary:**
1. ✅ Create Railway account
2. ✅ Connect GitHub repo
3. ✅ Add PostgreSQL database
4. ✅ Set environment variables
5. ✅ Set startup command
6. ✅ Monitor logs
7. ✅ Test in Discord
8. ✅ Bot is live!

**Time to deploy:** ~5 minutes

**Cost:** Free! (500 hours/month = ~21 days continuous)

---

**Your bot is now live on Railway! 🚀**

Check Railway dashboard for logs and monitor your bot 24/7!

Questions? Check Railway docs or see main README.md for troubleshooting.
