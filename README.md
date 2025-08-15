# Telegram Conversation Bot

This is a Telegram bot that helps you manage conversations from an external platform. It allows you to fetch conversations, send messages, and send emails to single or multiple conversations.

## Features

- Fetch conversations from "all" or "email" channels.
- Send text messages to a single conversation.
- Send emails to a single conversation.
- Broadcast text messages to all fetched conversations.
- Broadcast emails to all fetched conversations with a valid email address.
- Configure API token, environment ID, mailbox ID, and from-email address via commands.
- Uses inline buttons for a better user experience.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create a `.env` file:**
   Create a `.env` file in the root directory of the project and add the following variables:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   API_AUTHORIZATION_TOKEN=your_api_authorization_token
   ENVIRONMENT_ID=your_environment_id
   MAILBOX_ID=your_mailbox_id
   FROM_EMAIL=your_from_email_address
   ```
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from BotFather.
   - `API_AUTHORIZATION_TOKEN`: Your authorization token for the conversations API.
   - `ENVIRONMENT_ID`: The environment ID for the conversations API.
   - `MAILBOX_ID`: The mailbox ID to be used for sending emails.
   - `FROM_EMAIL`: The email address to send emails from.

   You can also set these values via commands after starting the bot.

## How to Run

1. Make sure you have completed the setup steps.
2. Run the bot:
   ```bash
   python bot.py
   ```

## Commands

- `/start`: Starts the bot and shows a welcome message.
- `/set_token <token>`: Sets the API authorization token.
- `/set_env_id <env_id>`: Sets the environment ID.
- `/set_mailbox_id <mailbox_id>`: Sets the mailbox ID for sending emails.
- `/set_from_email <email>`: Sets the "from" email address for sending emails.
- `/view_config`: Shows the current configuration.
- `/fetch_conversations [all|email]`: Starts fetching conversations in the background. You can specify `all` or `email` channel.
- `/stop_fetching`: Stops the background fetching of conversations.
- `/status`: Shows the number of fetched conversations.
- `/send`: Starts a conversation to send a message or an email.
- `/cancel`: Cancels the current operation.
