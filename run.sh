#!/bin/bash

# Discord Bot Runner Script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🤖 Discord Bot Launcher${NC}"
echo "================================"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo -e "${YELLOW}Please copy .env.example to .env and configure it:${NC}"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found!${NC}"
    echo -e "${YELLOW}Please install Python 3.8 or higher${NC}"
    exit 1
fi

# Check if venv exists, create if not
if [ ! -d venv ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install/update dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -q -r requirements.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to install dependencies${NC}"
    exit 1
fi

# Run the bot
echo -e "${GREEN}✅ Starting bot...${NC}"
echo "Press Ctrl+C to stop"
echo ""

python -m bot.main
