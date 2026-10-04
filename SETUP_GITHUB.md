# GitHub Setup Guide 🔧

Push your Discord bot code to GitHub so you can deploy it to Railway!

---

## Step 1: Create GitHub Account (if you don't have one)

1. Go to [github.com](https://github.com)
2. Click "Sign up"
3. Enter email, password, username
4. Complete verification
5. You now have a GitHub account! ✅

---

## Step 2: Create New Repository

### Option A: Via GitHub Website (Easiest)

1. Go to [github.com/new](https://github.com/new)
2. Fill in:
   - **Repository name**: `discord-bot`
   - **Description**: `Discord bot with activity tracking and fun replies`
   - **Visibility**: `Public` (required for Railway free tier)
   - ✅ Check "Add a README file" (optional)
3. Click "Create repository"
4. You now have an empty GitHub repo! ✅

**Copy the repository URL** - You'll need it in next step!

Example: `https://github.com/YOUR_USERNAME/discord-bot.git`

### Option B: Via GitHub CLI (If you have it installed)

```bash
gh repo create discord-bot --public --source=. --remote=origin --push
```

---

## Step 3: Push Your Bot Code to GitHub

Open terminal/PowerShell in the `discord-bot` folder:

```bash
cd /home/claude/discord-bot
```

### Initialize Git

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Set Up Repository

```bash
# Initialize git
git init

# Add all files
git add .

# Create first commit
git commit -m "Initial commit: Discord bot with activity tracking, fun replies, and daily throwback"

# Add remote (replace URL with your repo URL)
git remote add origin https://github.com/YOUR_USERNAME/discord-bot.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

**Expected output:**
```
Enumerating objects: XX, done.
Counting objects: 100% (XX/XX), done.
Delta compression using up to X threads
Compressing objects: 100% (XX/XX), done.
Writing objects: 100% (XX/XX), done.
Total XX (delta XX), reused XX (delta XX), pack-reused 0
remote: Resolving deltas: 100% (XX/XX), done.
To https://github.com/YOUR_USERNAME/discord-bot.git
 * [new branch]      main -> main
Branch 'main' is set up to track remote branch 'main' from 'origin'.
```

✅ **Your code is now on GitHub!**

---

## Step 4: Verify on GitHub

1. Go to `https://github.com/YOUR_USERNAME/discord-bot`
2. You should see all your files:
   - ✅ bot/ folder
   - ✅ database/ folder
   - ✅ requirements.txt
   - ✅ SETUP guides
   - ✅ .env.example
   - ✅ run.sh / run.bat
3. Everything looks good! ✅

---

## Step 5: Make Future Updates (Optional)

When you make changes locally:

```bash
cd discord-bot

# See what changed
git status

# Stage changes
git add .

# Commit changes
git commit -m "Description of what changed"

# Push to GitHub
git push origin main
```

Railway will automatically deploy when you push to GitHub!

---

## Troubleshooting

### "fatal: not a git repository"

```bash
# Make sure you're in the right directory
cd /home/claude/discord-bot

# Then initialize
git init
```

### "fatal: destination path 'discord-bot' already exists"

```bash
# You already have git initialized
# Just add remote and push
git remote add origin https://github.com/YOUR_USERNAME/discord-bot.git
git branch -M main
git push -u origin main
```

### "Authentication failed"

You need to set up GitHub authentication. Choose one:

**Option A: Personal Access Token (Recommended)**

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click "Generate new token"
3. Select:
   - ✅ repo (full control)
   - ✅ admin:repo_hook
4. Copy token
5. When git asks for password, paste the token

**Option B: SSH Key (Advanced)**

```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your.email@example.com"

# Add to GitHub: https://github.com/settings/keys
```

---

## What's Your GitHub URL?

After pushing, your bot will be at:

```
https://github.com/YOUR_USERNAME/discord-bot
```

Use this URL in Railway deployment!

---

## Next Steps

1. ✅ Create GitHub account
2. ✅ Create repository
3. ✅ Push bot code
4. ➡️ **Follow SETUP_RAILWAY.md to deploy!**

---

**Your code is now safe on GitHub and ready for Railway deployment! 🚀**
