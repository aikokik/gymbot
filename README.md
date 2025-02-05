# GymBot 🏋️‍♂️

A Telegram bot that creates personalized workout plans and integrates with Google Calendar for scheduling workouts.

## Features

- 🎯 Creates personalized workout plans based on:
  - Fitness level (beginner/intermediate/advanced)
  - Fitness goals (strength/weight loss/muscle gain/endurance/flexibility)
  - Weekly schedule availability
  - Session duration preferences
  - Available equipment
  - Target muscle groups
  - Medical limitations

- 📅 Google Calendar Integration:
  - Automatically suggests workout times based on your calendar availability
  - Schedules workouts directly to your Google Calendar
  - Manages workout event creation and scheduling

## Commands

- `/start` - Initialize the bot and get welcome message
- `/help` - Display available commands and usage instructions
- `/start_plan` - Begin creating your personalized workout plan
- `/create_plan` - Generate your workout plan based on your profile
- `/connect_calendar` - Link your Google Calendar for workout scheduling
- `/end` - End current session and clear chat history

## Setup

### Prerequisites

- Python 3.8 or higher
- Telegram Bot API token
- Google Calendar API credentials

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/gymbot.git
cd gymbot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```
OPENAI_API_KEY = your key here 
TELEGRAM_BOT_TOKEN = your key here 
```

### Google Calendar Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Google Calendar API
4. Create OAuth 2.0 credentials
5. Download the credentials file and save it to the root path under "client_secrets.json"

## Running the Bot

1. Start the bot:
```
make run
```

2. Open Telegram and search for your bot
3. Start a conversation with `/start`

## Logging

Logs are stored in the `logs` directory with the following structure:
- Application logs: `logs/app.log`
- Error logs: `logs/error.log`

## Error Handling

This bot is a simple implementation and may have limitations. Known potential issues include:
- Slow request to LLM (can be improved with caching query)
