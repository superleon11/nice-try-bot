# PostgreSQL Setup Guide 🗄️

Complete guide to set up PostgreSQL for your Discord bot.

## Overview

You have **two options**:
1. **Local PostgreSQL** (for testing/development) - Full control, free
2. **Railway PostgreSQL** (for production) - Hosted, easy scaling

This guide covers both!

---

## Option 1: Local PostgreSQL Setup

### macOS

#### Method A: Homebrew (Recommended)

```bash
# Install PostgreSQL
brew install postgresql@15

# Start PostgreSQL service
brew services start postgresql@15

# Verify installation
psql --version
```

#### Method B: Postgres.app

1. Download [Postgres.app](https://postgresapp.com)
2. Move to Applications folder
3. Launch Postgres.app
4. Start server from app menu

### Linux (Ubuntu/Debian)

```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql  # Auto-start on boot

# Verify installation
psql --version
```

### Windows

1. Download installer from [postgresql.org](https://www.postgresql.org/download/windows/)
2. Run installer
3. Set password for `postgres` user (remember this!)
4. Keep default settings:
   - Port: 5432
   - Locale: Default
5. Click "Finish"

**Optional**: Add PostgreSQL to PATH
- System Properties → Environment Variables → Add `C:\Program Files\PostgreSQL\15\bin` to PATH

---

## Create Database

### macOS/Linux

```bash
# Open psql prompt
psql

# Inside psql, create database
CREATE DATABASE discord_bot;

# List databases
\l

# Exit
\q
```

### Windows (PowerShell as Administrator)

```powershell
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE discord_bot;

# Exit
\q
```

---

## Get Connection String

This is what goes in your `.env` file as `DATABASE_URL`.

### Find Connection Details

**Default PostgreSQL settings:**
- Host: `localhost` (or `127.0.0.1`)
- Port: `5432`
- Database: `discord_bot`
- Username: `postgres` (or your username)
- Password: (what you set during installation, or empty)

### Connection String Format

```
postgresql+asyncpg://username:password@localhost:5432/discord_bot
```

**Examples:**

**macOS (default, no password):**
```
postgresql+asyncpg://postgres@localhost:5432/discord_bot
```

**Windows (with password):**
```
postgresql+asyncpg://postgres:your_password@localhost:5432/discord_bot
```

**With username created during setup:**
```
postgresql+asyncpg://jordan:mypassword@localhost:5432/discord_bot
```

---

## Test Connection

### Method 1: Using psql

```bash
# Test connection
psql -U postgres -d discord_bot -h localhost

# If successful, you'll see:
# psql (15.0)
# Type "help" for help.
# discord_bot=#

# Exit
\q
```

### Method 2: Using Python

```bash
# From your bot directory
python3 << 'EOF'
import asyncpg
import asyncio

async def test():
    try:
        # Change this to your connection string
        conn = await asyncpg.connect(
            user='postgres',
            password='',  # Leave empty if no password
            database='discord_bot',
            host='localhost',
            port=5432
        )
        print("✅ Database connection successful!")
        await conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

asyncio.run(test())
EOF
```

---

## Troubleshooting

### "Connection refused"
**Problem:** PostgreSQL not running

**Solution:**
```bash
# macOS
brew services start postgresql@15

# Linux
sudo systemctl start postgresql

# Windows (Services app)
# Search "Services" → Find "PostgreSQL" → Click Start
```

### "Role 'postgres' does not exist"
**Problem:** Different username setup

**Solution:**
```bash
# List all roles
psql -l

# Use the username shown in the list
psql -U your_username
```

### "Database 'discord_bot' does not exist"
**Problem:** Database not created

**Solution:**
```bash
psql -U postgres
CREATE DATABASE discord_bot;
\q
```

### "Password authentication failed"
**Problem:** Wrong password

**Solution:**
- macOS/Linux: PostgreSQL often has no password by default
  ```
  # Try without password:
  psql -U postgres
  ```
- Windows: Use password you set during installation

### "Port 5432 already in use"
**Problem:** PostgreSQL or other service using port

**Solution:**
```bash
# Find process using port 5432
lsof -i :5432  # macOS/Linux
netstat -ano | findstr :5432  # Windows

# Kill process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows
```

---

## Verify Database Setup

```bash
# Connect to database
psql -U postgres -d discord_bot

# Run inside psql:
# Check if empty (should return no results)
SELECT * FROM information_schema.tables WHERE table_schema = 'public';

# Exit
\q
```

The tables will be created automatically when your bot starts!

---

## Option 2: Railway PostgreSQL (Recommended for Production)

See **SETUP_RAILWAY.md** for hosted PostgreSQL setup.

---

## Next Steps

1. ✅ Install PostgreSQL locally
2. ✅ Create `discord_bot` database
3. ✅ Get connection string
4. ✅ Add to `.env` file as `DATABASE_URL`
5. Continue with bot testing!

---

## Quick Reference

### macOS
```bash
brew install postgresql@15
brew services start postgresql@15
psql
CREATE DATABASE discord_bot;
\q
```

### Linux
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
psql
CREATE DATABASE discord_bot;
\q
```

### Windows (PowerShell Admin)
```powershell
# After installer
psql -U postgres
CREATE DATABASE discord_bot;
\q
```

---

**Need help? Check Troubleshooting section above! ⬆️**
