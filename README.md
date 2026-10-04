# Discord Fun Bot 🎉

A fun Discord bot with intelligent replies, activity tracking, and a daily "Throwback of the Day" feature.

## Features

### 1. **Fun Replies** 🤖
- Responds to messages with witty, entertaining replies
- Mix of styles: sarcastic, meme-based, and wholesome
- Smart rate limiting to prevent spam (replies not on every message)
- Keyword-based trigger detection

### 2. **Activity Tracking** 📊
- Tracks user messages sent in channels
- Monitors voice channel time
- Builds comprehensive activity profiles

### 3. **Statistics & Leaderboards** 🏆
- `!mystats` - View your personal activity stats
- `!leaderboard [metric]` - View server rankings
  - Metrics: `messages`, `voice`, `combined`
- See your rank and engagement score

### 4. **Throwback of the Day** 📼
- Daily random message from server history
- Posts automatically at configured time (default: 2 AM UTC)
- Excludes bot messages, shows metadata

## Setup Instructions

### Prerequisites
- Python 3.8+
- PostgreSQL database (local or remote)
- Discord server (for testing)
- Discord bot token

### Step 1: Clone/Create Project

```bash
cd discord-bot
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Set Up Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Go to "Bot" section, click "Add Bot"
4. Copy the bot token
5. Go to "OAuth2" → "URL Generator"
6. Select scopes: `bot`
7. Select permissions:
   - Read Messages/View Channels
   - Send Messages
   - Read Message History
   - Connect
   - Speak
8. Copy the generated URL and open in browser to invite bot to your server

### Step 4: Set Up Database

#### Option A: Local PostgreSQL

```bash
# Install PostgreSQL if you haven't
# macOS
brew install postgresql

# Linux (Ubuntu/Debian)
sudo apt-get install postgresql

# Windows
# Download from https://www.postgresql.org/download/windows/

# Create database
createdb discord_bot

# Or using psql
psql
CREATE DATABASE discord_bot;
\q
```

#### Option B: Hosted PostgreSQL

Use services like:
- **Railway** (recommended - free tier included)
- **Heroku Postgres**
- **ElephantSQL**
- **AWS RDS**

### Step 5: Configure Environment

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your values:
   ```
   DISCORD_TOKEN=your_bot_token_here
   DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/discord_bot
   GUILD_ID=your_server_id
   THROWBACK_CHANNEL_ID=your_channel_id
   ```

To get IDs:
- Enable Developer Mode in Discord settings
- Right-click server/channel and "Copy Server/Channel ID"

### Step 6: Run the Bot

```bash
python -m bot.main
```

You should see:
```
Bot logged in as YourBotName#1234
```

## Commands

### User Commands

```bash
!mystats              # View your activity stats
!leaderboard messages # View message leaderboard
!leaderboard voice    # View voice time leaderboard
!leaderboard combined # View combined engagement leaderboard
!mystats_top3         # Check if you're in top 3
```

### Admin Commands

```bash
!throwback_now        # Manually trigger throwback (testing)
!throwback_set 2 0    # Set daily time (2:00 AM UTC)
!throwback_stats      # View throwback configuration
!addfunresponse category text  # Add custom response
!funresponses         # List all response categories
```

## Project Structure

```
discord-bot/
├── bot/
│   ├── main.py                 # Bot entry point
│   ├── cogs/
│   │   ├── activity_tracking.py # Message & voice tracking
│   │   ├── fun_replies.py       # Fun response system
│   │   ├── stats_commands.py    # !mystats & !leaderboard
│   │   └── throwback.py         # Daily throwback task
│   └── utils/
│       ├── db.py               # Database operations
│       └── config.py           # Configuration management
├── database/
│   └── models.py              # SQLAlchemy ORM models
├── .env                        # Environment variables (create from .env.example)
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Database Schema

### Tables
- **users** - Discord user information
- **messages** - Message records for throwback & stats
- **voice_sessions** - Voice channel activity
- **user_activity_summary** - Cached stats for fast queries
- **reply_responses** - Fun bot responses
- **fun_reply_tracking** - Rate limiting data

## Deployment

### Option 1: Railway (Recommended)

1. **Create Railway Account**
   - Sign up at [railway.app](https://railway.app)

2. **Create PostgreSQL Database**
   - New Project → Add PostgreSQL
   - Copy connection string from "Connect" tab

3. **Deploy Bot**
   - Connect GitHub repo
   - Set environment variables
   - Deploy

4. **Keep Bot Running**
   - Railway supports background jobs
   - Bot will run continuously

### Option 2: Local Server/VPS

1. Install Python and PostgreSQL on server
2. Clone repository
3. Set up `.env` file
4. Install dependencies
5. Run with process manager:
   ```bash
   # Using screen
   screen -S discord-bot python -m bot.main
   
   # Using systemd
   # Create /etc/systemd/system/discord-bot.service
   # Enable and start
   ```

### Option 3: Docker

1. Create `Dockerfile`:
   ```dockerfile
   FROM python:3.11-slim
   
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   
   COPY . .
   
   CMD ["python", "-m", "bot.main"]
   ```

2. Deploy to container service (Docker Hub, Heroku, AWS ECR)

## Troubleshooting

### Bot Not Responding

1. Check Discord token in `.env` is correct
2. Verify bot has message permissions in server
3. Check `bot.log` for errors
4. Ensure MESSAGE_CONTENT intent is enabled

### Activity Not Tracking

1. Verify database connection string in `.env`
2. Check PostgreSQL is running
3. Look for errors in `bot.log`
4. Test database connection:
   ```bash
   psql "your_database_url"
   ```

### Bot Not Posting Throwback

1. Verify THROWBACK_CHANNEL_ID is correct
2. Check bot has Send Messages permission in channel
3. Ensure messages exist in server history
4. Check `bot.log` for scheduler errors

### Database Connection Errors

```
"could not connect to server: Connection refused"
```

- PostgreSQL not running: `brew services start postgresql`
- Wrong credentials: Check `.env` DATABASE_URL
- Database doesn't exist: `createdb discord_bot`

## Configuration Guide

### Fun Replies

Edit `bot/utils/config.py`:
```python
FUN_REPLY_MIN_INTERVAL_SECONDS = 300  # 5 minutes between replies
FUN_REPLY_ENABLED = True
```

### Throwback Timing

Set in `bot/utils/config.py`:
```python
THROWBACK_HOUR = 2        # 2 AM UTC
THROWBACK_MINUTE = 0
THROWBACK_ENABLED = True
```

Or use admin command:
```
!throwback_set 2 0
```

## Performance Tips

1. **Message Indexing**: Database already indexed for fast queries
2. **Leaderboard Caching**: Pre-calculated summaries for speed
3. **Rate Limiting**: Prevents bot spam
4. **Voice Session Memory**: Efficient tracking during runtime

## Future Enhancements

- [ ] Custom response builder GUI
- [ ] Per-channel activity tracking
- [ ] Monthly achievement badges
- [ ] Streak tracking (consecutive days active)
- [ ] Custom commands builder
- [ ] Web dashboard for stats
- [ ] Message reaction tracking
- [ ] Role-based activity multipliers

## License

MIT License - feel free to modify and use!

## Support

For issues or questions:
1. Check `bot.log` for error messages
2. Verify all environment variables are set
3. Ensure Discord bot has proper permissions
4. Check PostgreSQL is running and accessible

---

**Happy botting! 🚀**
