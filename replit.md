# Discord Immunity Bot

## Overview
A Discord bot that manages character immunities with automatic 48-hour expiration tracking and notifications. Supports multiple servers with channel-based restrictions.

## Project Status
✅ Bot is live and running as **Imunidade#7699** with all features operational.

## Features
### Immunity Commands (Only in channels with "imunidade" in name)
- `/imune_add` - Register one immune character per user with game/anime origin
- `/imune_lista` - Display all active immunities with remaining hours
- `/imune_remover` - Manually remove your immunity

### Multi-Server Support
- Each server has its own immunity list
- Commands only work in channels containing "imunidade" in the channel name
- Automatic notifications sent to the first channel with "imunidade" in name

### Automatic System
- Automatic hourly checks for expired immunities (48-hour duration)
- Searches for channels with "imunidade" in name to send notifications
- JSON-based data persistence organized by server

## Setup Required
The bot needs valid Discord credentials:

1. **Bot Token**: Get from Discord Developer Portal
   - Visit: https://discord.com/developers/applications
   - Create a new application or select existing
   - Go to "Bot" section
   - Click "Reset Token" and copy the token
   - Required intents: MESSAGE CONTENT INTENT
   - Required permissions: Send Messages, Read Messages/View Channels, Use Slash Commands

2. **Channel ID**: Numeric ID where bot sends notifications
   - Enable Developer Mode in Discord settings
   - Right-click target text channel → Copy Channel ID
   - Should be a long number (e.g., 1234567890123456789)

## Technical Stack
- Python 3.11
- discord.py 2.6.3
- JSON file storage (imunidades.json)
- Slash commands with discord.py app_commands

## Files
- `bot.py` - Main bot implementation
- `imunidades.json` - Data persistence (auto-generated)

## Recent Changes
- 2025-10-05: Initial bot implementation
- Added error handling for invalid credentials and malformed JSON files
- Added channel type validation for notifications
- Implemented multi-server support with guild-based data storage
- Added channel name restriction: commands only work in channels with "imunidade" in name
- Automatic channel detection for expiration notifications based on channel name
- Removed fixed channel ID system in favor of dynamic channel detection
