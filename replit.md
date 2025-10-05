# Discord Immunity Bot

## Overview
A Discord bot that manages character immunities with automatic 48-hour expiration tracking and notifications.

## Project Status
Bot implementation is complete. Waiting for valid Discord credentials to test functionality.

## Features
- `/imune_add` - Register one immune character per user with game/anime origin
- `/imune_lista` - Display all active immunities with remaining hours
- `/imune_remover` - Manually remove your immunity
- Automatic hourly checks for expired immunities (48-hour duration)
- Automated expiration notifications sent to designated Discord channel
- JSON-based data persistence

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
- Added error handling for invalid credentials
- Added channel type validation for notifications
