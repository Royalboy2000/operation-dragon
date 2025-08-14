import logging
import os
import threading
import time

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import api_client

# Conversation states
(
    SELECTING_ACTION,
    SELECTING_RECIPIENT,
    ENTERING_CONV_ID,
    ENTERING_MESSAGE,
    ENTERING_SUBJECT,
    ENTERING_BODY,
    BROADCASTING_MESSAGE,
    BROADCASTING_EMAIL_SUBJECT,
    BROADCASTING_EMAIL_BODY,
) = range(9)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Global dicts to store config and data
bot_data = {
    "api_token": os.getenv("API_AUTHORIZATION_TOKEN"),
    "env_id": os.getenv("ENVIRONMENT_ID"),
    "mailbox_id": os.getenv("MAILBOX_ID"),
    "from_email": os.getenv("FROM_EMAIL"),
    "conversations": {},
    "stop_fetching": False,
    "fetching_thread": None,
}


def fetch_worker():
    """The worker function that fetches conversations."""
    while not bot_data.get("stop_fetching", False):
        try:
            token = bot_data.get("api_token")
            env_id = bot_data.get("env_id")
            channel = bot_data.get("fetch_channel")
            if not token or not env_id:
                logger.warning("API token or env_id not set. Stopping worker.")
                break

            logger.info(f"Fetching conversations for channel: {channel or 'all'}")
            data = api_client.search_conversations(token, env_id, channel)
            conversations = data.get("data", {}).get("searchConversations", [])
            for conv in conversations:
                bot_data["conversations"][conv["conversationId"]] = conv
            logger.info(f"Fetched {len(conversations)} conversations.")

        except Exception as e:
            logger.error(f"Error fetching conversations: {e}")

        time.sleep(10)


async def _fetch_conversations_action(update: Update, context: ContextTypes.DEFAULT_TYPE, channel: str = None):
    """Internal action to start fetching conversations."""
    if bot_data.get("fetching_thread") and bot_data["fetching_thread"].is_alive():
        await update.effective_message.reply_text("Already fetching conversations.")
        return

    bot_data["fetch_channel"] = channel
    bot_data["stop_fetching"] = False
    thread = threading.Thread(target=fetch_worker)
    thread.start()
    bot_data["fetching_thread"] = thread
    await update.effective_message.reply_text(f"Started fetching conversations for channel: {channel or 'all'}.")

async def fetch_conversations_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command to start fetching conversations."""
    channel = None
    if context.args:
        if context.args[0] in ["email", "all"]:
            channel = context.args[0] if context.args[0] != "all" else None
        else:
            await update.message.reply_text("Usage: /fetch_conversations [all|email]")
            return
    await _fetch_conversations_action(update, context, channel)


async def stop_fetching(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops fetching conversations."""
    if bot_data.get("fetching_thread") and bot_data["fetching_thread"].is_alive():
        bot_data["stop_fetching"] = True
        bot_data["fetching_thread"].join()
        await update.effective_message.reply_text("Stopped fetching conversations.")
    else:
        await update.effective_message.reply_text("Not currently fetching conversations.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the number of fetched conversations."""
    conversations = bot_data.get("conversations", {})
    email_count = sum(1 for conv in conversations.values() if conv.get('contact', {}).get('email'))

    message = (
        f"Total conversations fetched: {len(conversations)}\n"
        f"Conversations with email: {email_count}"
    )
    await update.effective_message.reply_text(message)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    keyboard = [
        [InlineKeyboardButton("Fetch (All)", callback_data="fetch_all"),
         InlineKeyboardButton("Fetch (Email)", callback_data="fetch_email")],
        [InlineKeyboardButton("Stop Fetching", callback_data="stop_fetching")],
        [InlineKeyboardButton("Status", callback_data="status")],
        [InlineKeyboardButton("Send Message/Email", callback_data="send")],
        [InlineKeyboardButton("View Config", callback_data="view_config")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome! Please choose an action:", reply_markup=reply_markup)

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles main menu button clicks that are not conversations."""
    query = update.callback_query
    await query.answer()

    if query.data == "fetch_all":
        await _fetch_conversations_action(update, context, channel=None)
    elif query.data == "fetch_email":
        await _fetch_conversations_action(update, context, channel="email")
    elif query.data == "stop_fetching":
        await stop_fetching(update, context)
    elif query.data == "status":
        await status(update, context)
    elif query.data == "view_config":
        await view_config(update, context)


async def set_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the API authorization token."""
    if context.args:
        bot_data["api_token"] = context.args[0]
        await update.message.reply_text("API token set.")
    else:
        await update.message.reply_text("Usage: /set_token <token>")


async def set_env_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the environment ID."""
    if context.args:
        bot_data["env_id"] = context.args[0]
        await update.message.reply_text("Environment ID set.")
    else:
        await update.message.reply_text("Usage: /set_env_id <env_id>")


async def set_mailbox_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the mailbox ID."""
    if context.args:
        bot_data["mailbox_id"] = context.args[0]
        await update.message.reply_text("Mailbox ID set.")
    else:
        await update.message.reply_text("Usage: /set_mailbox_id <mailbox_id>")


async def set_from_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the from email address."""
    if context.args:
        bot_data["from_email"] = context.args[0]
        await update.message.reply_text("From email set.")
    else:
        await update.message.reply_text("Usage: /set_from_email <email>")


async def view_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Views the current configuration."""
    token = bot_data.get("api_token", "Not set")
    env_id = bot_data.get("env_id", "Not set")
    mailbox_id = bot_data.get("mailbox_id", "Not set")
    from_email = bot_data.get("from_email", "Not set")
    message = (
        f"Current configuration:\n"
        f"API Token: {token}\n"
        f"Environment ID: {env_id}\n"
        f"Mailbox ID: {mailbox_id}\n"
        f"From Email: {from_email}"
    )
    await update.effective_message.reply_text(message)


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to send a message or email."""
    keyboard = [
        [InlineKeyboardButton("Send a message", callback_data="send_message")],
        [InlineKeyboardButton("Send an email", callback_data="send_email")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        # Replying to the original message to start a new flow
        await update.callback_query.message.reply_text("Let's send something! What would you like to do?", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Let's send something! What would you like to do?", reply_markup=reply_markup)

    return SELECTING_ACTION


async def select_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection of action (message or email)."""
    query = update.callback_query
    await query.answer()
    context.user_data["action"] = query.data

    keyboard = [
        [InlineKeyboardButton("To a single conversation", callback_data="single")],
        [InlineKeyboardButton("Broadcast to all", callback_data="broadcast")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text="Send to a single conversation or broadcast to all?", reply_markup=reply_markup
    )
    return SELECTING_RECIPIENT


async def select_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection of recipient (single or broadcast)."""
    query = update.callback_query
    await query.answer()
    recipient_type = query.data
    context.user_data["recipient_type"] = recipient_type

    action = context.user_data.get("action")
    if recipient_type == "single":
        await query.edit_message_text(text="Please enter the conversation ID.")
        return ENTERING_CONV_ID
    # broadcast
    elif action == "send_message":
        await query.edit_message_text(text="Please enter the message to broadcast.")
        return BROADCASTING_MESSAGE
    else:  # send_email
        await query.edit_message_text(text="Please enter the subject for the email broadcast.")
        return BROADCASTING_EMAIL_SUBJECT


async def enter_conv_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the conversation ID input."""
    context.user_data["conv_id"] = update.message.text
    action = context.user_data.get("action")
    if action == "send_message":
        await update.message.reply_text("Please enter the message.")
        return ENTERING_MESSAGE
    else:  # send_email
        await update.message.reply_text("Please enter the subject of the email.")
        return ENTERING_SUBJECT


async def enter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the message input and sends the message."""
    message_text = update.message.text
    conv_id = context.user_data["conv_id"]
    token = bot_data.get("api_token")
    env_id = bot_data.get("env_id")

    if not all([token, env_id]):
        await update.message.reply_text("Configuration is not set. Please use /set_token and /set_env_id.")
        return ConversationHandler.END

    try:
        api_client.send_text_message(token, env_id, conv_id, message_text)
        await update.message.reply_text("Message sent successfully.")
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        await update.message.reply_text(f"Failed to send message: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def enter_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the subject input."""
    context.user_data["subject"] = update.message.text
    await update.message.reply_text("Please enter the body of the email.")
    return ENTERING_BODY


async def enter_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the body input and sends the email."""
    body = update.message.text
    conv_id = context.user_data["conv_id"]
    subject = context.user_data["subject"]

    token = bot_data.get("api_token")
    env_id = bot_data.get("env_id")
    mailbox_id = bot_data.get("mailbox_id")
    from_email = bot_data.get("from_email")

    conversations = bot_data.get("conversations", {})
    conversation = conversations.get(conv_id)
    if not conversation:
        await update.message.reply_text(f"Conversation {conv_id} not found.")
        context.user_data.clear()
        return ConversationHandler.END

    to_email = conversation.get("contact", {}).get("email")

    if not all([token, env_id, mailbox_id, from_email, to_email]):
        await update.message.reply_text(
            "Configuration is not fully set or email not found for this conversation. Please check config and data."
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        api_client.send_email(token, env_id, mailbox_id, conv_id, from_email, to_email, subject, body)
        await update.message.reply_text("Email sent successfully.")
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        await update.message.reply_text(f"Failed to send email: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the broadcast message input and sends it."""
    message_text = update.message.text
    token = bot_data.get("api_token")
    env_id = bot_data.get("env_id")

    if not all([token, env_id]):
        await update.message.reply_text("Configuration is not set. Please use /set_token and /set_env_id.")
        return ConversationHandler.END

    conversations = bot_data.get("conversations", {}).values()
    if not conversations:
        await update.message.reply_text("No conversations fetched to broadcast to.")
        return ConversationHandler.END

    success_count = 0
    error_count = 0
    for conv in conversations:
        try:
            api_client.send_text_message(token, env_id, conv["conversationId"], message_text)
            success_count += 1
        except Exception as e:
            logger.error(f"Error broadcasting message to {conv['conversationId']}: {e}")
            error_count += 1

    await update.message.reply_text(f"Broadcast finished. Sent: {success_count}, Failed: {error_count}.")
    context.user_data.clear()
    return ConversationHandler.END

async def broadcast_email_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the broadcast email subject input."""
    context.user_data["subject"] = update.message.text
    await update.message.reply_text("Please enter the body of the email for broadcast.")
    return BROADCASTING_EMAIL_BODY

async def broadcast_email_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the broadcast email body input and sends emails."""
    body = update.message.text
    subject = context.user_data["subject"]
    token = bot_data.get("api_token")
    env_id = bot_data.get("env_id")
    mailbox_id = bot_data.get("mailbox_id")
    from_email = bot_data.get("from_email")

    if not all([token, env_id, mailbox_id, from_email]):
        await update.message.reply_text("Configuration is not fully set. Please check config.")
        return ConversationHandler.END

    conversations = bot_data.get("conversations", {}).values()
    email_conversations = [
        c for c in conversations if c.get("contact", {}).get("email")
        and "zenka.co.ke" not in c.get("contact", {}).get("email")
    ]

    if not email_conversations:
        await update.message.reply_text("No conversations with valid emails found to broadcast to.")
        return ConversationHandler.END

    success_count = 0
    error_count = 0
    for conv in email_conversations:
        to_email = conv["contact"]["email"]
        conv_id = conv["conversationId"]
        try:
            api_client.send_email(token, env_id, mailbox_id, conv_id, from_email, to_email, subject, body)
            success_count += 1
        except Exception as e:
            logger.error(f"Error broadcasting email to {to_email} ({conv_id}): {e}")
            error_count += 1

    await update.message.reply_text(f"Email broadcast finished. Sent: {success_count}, Failed: {error_count}.")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in .env file. Please set it.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("send", send_command), CallbackQueryHandler(send_command, pattern="^send$")],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(select_action, pattern="^send_message$|^send_email$")
            ],
            SELECTING_RECIPIENT: [
                CallbackQueryHandler(select_recipient, pattern="^single$|^broadcast$")
            ],
            ENTERING_CONV_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_conv_id)],
            ENTERING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_message)],
            ENTERING_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_subject)],
            ENTERING_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_body)],
            BROADCASTING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)
            ],
            BROADCASTING_EMAIL_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_email_subject)
            ],
            BROADCASTING_EMAIL_BODY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_email_body)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    application.add_handler(conv_handler)

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_token", set_token))
    application.add_handler(CommandHandler("set_env_id", set_env_id))
    application.add_handler(CommandHandler("set_mailbox_id", set_mailbox_id))
    application.add_handler(CommandHandler("set_from_email", set_from_email))
    application.add_handler(CommandHandler("view_config", view_config))
    application.add_handler(CommandHandler("fetch_conversations", fetch_conversations_command))
    application.add_handler(CommandHandler("stop_fetching", stop_fetching))
    application.add_handler(CommandHandler("status", status))

    # This handler must be added after the conversation handler to not catch the 'send' callback
    application.add_handler(CallbackQueryHandler(main_menu_callback))


    application.run_polling()


if __name__ == "__main__":
    main()
