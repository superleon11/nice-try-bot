#!/bin/bash

# Push Discord Bot to GitHub
# Usage: ./push_to_github.sh https://github.com/YOUR_USERNAME/discord-bot.git

echo "🚀 Discord Bot GitHub Push Script"
echo "=================================="
echo ""

# Check if repo URL provided
if [ -z "$1" ]; then
    echo "❌ No GitHub URL provided!"
    echo ""
    echo "Usage: ./push_to_github.sh https://github.com/YOUR_USERNAME/discord-bot.git"
    echo ""
    echo "Steps:"
    echo "1. Create repo at https://github.com/new"
    echo "2. Copy the repo URL (https://github.com/YOUR_USERNAME/discord-bot.git)"
    echo "3. Run this script with that URL"
    echo ""
    exit 1
fi

REPO_URL=$1

echo "Repository URL: $REPO_URL"
echo ""

# Configure git (if not already configured)
echo "Setting up git configuration..."
git config --global user.name "Discord Bot User" 2>/dev/null || true
git config --global user.email "bot@discord.local" 2>/dev/null || true

# Initialize git
echo "Initializing git repository..."
if [ ! -d .git ]; then
    git init
    echo "✅ Git initialized"
else
    echo "✅ Git already initialized"
fi

# Add all files
echo "Adding files..."
git add .
echo "✅ Files added"

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo "⚠️  No changes to commit"
else
    # Create commit
    echo "Creating commit..."
    git commit -m "Discord bot: Initial commit with activity tracking, fun replies, and daily throwback"
    echo "✅ Commit created"
fi

# Check if remote already exists
if git remote | grep -q "^origin$"; then
    echo "Updating remote origin..."
    git remote remove origin
fi

# Add remote
echo "Adding remote..."
git remote add origin "$REPO_URL"
echo "✅ Remote added"

# Ensure main branch
echo "Checking branch..."
if ! git rev-parse --verify main >/dev/null 2>&1; then
    git branch -M main
    echo "✅ Branch set to main"
else
    echo "✅ Main branch exists"
fi

# Push to GitHub
echo ""
echo "Pushing to GitHub..."
echo "(You may be prompted for authentication)"
echo ""

git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Successfully pushed to GitHub!"
    echo ""
    echo "Your repository: $REPO_URL"
    echo ""
    echo "Next steps:"
    echo "1. Go to Railway.app"
    echo "2. Create new project"
    echo "3. Deploy from GitHub repo"
    echo "4. Follow SETUP_RAILWAY.md"
else
    echo ""
    echo "❌ Failed to push to GitHub"
    echo "Common issues:"
    echo "- Authentication failed: Check your GitHub credentials"
    echo "- Repository URL wrong: Verify the URL"
    echo "- Remote already exists: Check git remote -v"
    echo ""
    exit 1
fi
