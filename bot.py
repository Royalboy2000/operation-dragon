import logging
import os
import threading
import time
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from pyngrok import ngrok

import api_client
import database
from web_server import app as flask_app

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
    "stop_fetching": False,
    "fetching_thread": None,
    "web_server_thread": None,
    "public_url": None,
}

executor_fetch = ThreadPoolExecutor(max_workers=100)
executor_send_message = ThreadPoolExecutor(max_workers=100)
executor_send_email = ThreadPoolExecutor(max_workers=100)


def _process_and_save_conversation(conv, fetch_channel):
    """Process a single conversation and save it to the database."""
    conv_id = conv.get("conversationId")
    email = conv.get("contact", {}).get("email")
    channel_id = conv.get("channelId")

    if fetch_channel is None and channel_id == "email":
        return
    database.add_conversation(conv_id, email, channel_id)

def fetch_page(page, channel):
    """Fetches a single page of conversations and saves them."""
    try:
        token = bot_data.get("api_token")
        env_id = bot_data.get("env_id")
        if not token or not env_id:
            return 0

        data = api_client.search_conversations(token, env_id, page=page, channel=channel)
        conversations = data.get("data", {}).get("searchConversations", [])
        if not conversations:
            return 0

        for conv in conversations:
            _process_and_save_conversation(conv, channel)

        return len(conversations)
    except Exception as e:
        logger.error(f"Error fetching page {page}: {e}")
        return -1

def _scrape_all_pages(channel):
    """Scrapes all pages of conversations concurrently using a producer-consumer model."""
    database.clear_conversations()
    logger.info("Starting true unlimited concurrent scrape.")

    page_queue = queue.Queue()
    stop_event = threading.Event()

    # Start with a batch of pages
    for i in range(1, 101):
        page_queue.put(i)

    def consumer():
        """Consumes page numbers from the queue, fetches them, and adds more pages if necessary."""
        while not stop_event.is_set():
            try:
                page = page_queue.get_nowait()

                num_fetched = fetch_page(page, channel)

                if num_fetched == 100:
                    # This page was full, so there's probably a next page.
                    # Let's add the page 100 pages from now to the queue.
                    # This creates a rolling window of 100 concurrent requests.
                    next_page = page + 100
                    page_queue.put(next_page)
                elif num_fetched == 0:
                    # This page was empty, we are likely at the end.
                    # This is a heuristic to stop.
                    stop_event.set()

                page_queue.task_done()
            except queue.Empty:
                # No more pages in the queue, this worker can stop.
                break
            except Exception as e:
                logger.error(f"Error in consumer thread: {e}")
                break

    # Start consumers in the thread pool
    futures = [executor_fetch.submit(consumer) for _ in range(100)]

    # Wait for all futures to complete
    for future in as_completed(futures):
        try:
            future.result()
        except Exception as e:
            logger.error(f"A consumer thread raised an exception: {e}")

    # Final check to ensure the queue is empty
    page_queue.join()

    logger.info("Scraping finished.")
    bot_data["stop_fetching"] = True


def _monitor_first_page(channel):
    """Continuously fetches the first page of conversations."""
    while not bot_data.get("stop_fetching", False):
        fetch_page(1, channel)
        time.sleep(10)

def fetch_worker(mode, channel):
    """The worker function that fetches conversations."""
    if mode == "monitor":
        _monitor_first_page(channel)
    elif mode == "scrape":
        _scrape_all_pages(channel)

async def ask_for_fetching_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Asks the user for the fetching mode."""
    query = update.callback_query
    await query.answer()

    channel = None
    if query.data == "fetch_email":
        channel = "email"

    context.user_data["fetch_channel"] = channel

    keyboard = [
        [InlineKeyboardButton("Monitor First Page", callback_data="mode_monitor")],
        [InlineKeyboardButton("Scrape All Pages", callback_data="mode_scrape")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Please choose a fetching mode:", reply_markup=reply_markup)

async def set_fetching_mode_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the fetching mode and starts the worker."""
    query = update.callback_query
    await query.answer()

    mode = query.data.split("_")[1]
    channel = context.user_data.get("fetch_channel")

    if bot_data.get("fetching_thread") and bot_data["fetching_thread"].is_alive():
        await query.edit_message_text("Already fetching conversations.")
        return

    bot_data["stop_fetching"] = False
    thread = threading.Thread(target=fetch_worker, args=(mode, channel))
    thread.start()
    bot_data["fetching_thread"] = thread

    await query.edit_message_text(f"Started fetching conversations for channel '{channel or 'all'}' in '{mode}' mode.")


async def stop_fetching(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops fetching conversations."""
    if bot_data.get("fetching_thread") and bot_data["fetching_thread"].is_alive():
        bot_data["stop_fetching"] = True
        bot_data["fetching_thread"].join()
        await update.effective_message.reply_text("Stopped fetching conversations.")
    else:
        await update.effective_message.reply_text("Not currently fetching conversations.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the number of fetched conversations from the database."""
    all_convs = database.get_all_conversations()
    email_count = sum(1 for conv in all_convs if conv.get('email'))

    message = (
        f"Total conversations in DB: {len(all_convs)}\n"
        f"Conversations with email in DB: {email_count}"
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
        [InlineKeyboardButton("View Data", callback_data="view_data")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome! Please choose an action:", reply_markup=reply_markup)

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles main menu button clicks."""
    query = update.callback_query
    await query.answer()

    if query.data in ["fetch_all", "fetch_email"]:
        await ask_for_fetching_mode(update, context)
    elif query.data == "stop_fetching":
        await stop_fetching(update, context)
    elif query.data == "status":
        await status(update, context)
    elif query.data == "view_config":
        await view_config(update, context)
    elif query.data == "view_data":
        await view_data(update, context)


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
    elif action == "send_message":
        await query.edit_message_text(text="Please enter the message to broadcast.")
        return BROADCASTING_MESSAGE
    else:
        await query.edit_message_text(text="Please enter the subject for the email broadcast.")
        return BROADCASTING_EMAIL_SUBJECT


async def enter_conv_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the conversation ID input."""
    context.user_data["conv_id"] = update.message.text
    action = context.user_data.get("action")
    if action == "send_message":
        await update.message.reply_text("Please enter the message.")
        return ENTERING_MESSAGE
    else:
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

    all_convs = database.get_all_conversations()
    conv_map = {c['conversation_id']: c for c in all_convs}

    conversation = conv_map.get(conv_id)
    if not conversation:
        await update.message.reply_text(f"Conversation {conv_id} not found in database.")
        context.user_data.clear()
        return ConversationHandler.END

    to_email = conversation.get("email")

    if not all([token, env_id, mailbox_id, from_email, to_email]):
        await update.message.reply_text("Configuration is not fully set or email not found for this conversation.")
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

def _send_message_worker(conv_id, text):
    """Worker to send a single text message."""
    try:
        token = bot_data.get("api_token")
        env_id = bot_data.get("env_id")
        api_client.send_text_message(token, env_id, conv_id, text)
        return True
    except Exception as e:
        logger.error(f"Error sending message to {conv_id}: {e}")
        return False

def _send_email_worker(conv, subject, body):
    """Worker to send a single email."""
    try:
        token = bot_data.get("api_token")
        env_id = bot_data.get("env_id")
        mailbox_id = bot_data.get("mailbox_id")
        from_email = bot_data.get("from_email")
        to_email = conv["email"]
        conv_id = conv["conversation_id"]
        api_client.send_email(token, env_id, mailbox_id, conv_id, from_email, to_email, subject, body)
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email} ({conv_id}): {e}")
        return False

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the broadcast message input and sends it concurrently."""
    message_text = update.message.text
    await update.message.reply_text("Queueing broadcast... This may take a while.")

    conversations = database.get_all_conversations()
    if not conversations:
        await update.message.reply_text("No conversations in database to broadcast to.")
        return ConversationHandler.END

    futures = [executor_send_message.submit(_send_message_worker, conv["conversation_id"], message_text) for conv in conversations]

    success_count = sum(f.result() for f in as_completed(futures))

    await update.message.reply_text(f"Broadcast finished. Sent: {success_count}, Failed: {len(conversations) - success_count}.")
    context.user_data.clear()
    return ConversationHandler.END

async def broadcast_email_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the broadcast email body input and sends emails concurrently."""
    body = update.message.text
    subject = context.user_data["subject"]
    await update.message.reply_text("Queueing email broadcast... This may take a while.")

    all_convs = database.get_all_conversations()
    email_conversations = [c for c in all_convs if c.get("email") and "zenka.co.ke" not in c.get("email")]

    if not email_conversations:
        await update.message.reply_text("No conversations with valid emails found to broadcast to.")
        return ConversationHandler.END

    futures = [executor_send_email.submit(_send_email_worker, conv, subject, body) for conv in email_conversations]

    success_count = sum(f.result() for f in as_completed(futures))

    await update.message.reply_text(f"Email broadcast finished. Sent: {success_count}, Failed: {len(email_conversations) - success_count}.")
    context.user_data.clear()
    return ConversationHandler.END

async def broadcast_email_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the broadcast email subject input."""
    context.user_data["subject"] = update.message.text
    await update.message.reply_text("Please enter the body of the email for broadcast.")
    return BROADCASTING_EMAIL_BODY


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

async def view_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts a web server to view the database content and provides a public URL."""
    if bot_data.get("web_server_thread") and bot_data["web_server_thread"].is_alive():
        public_url = bot_data.get("public_url")
        await update.effective_message.reply_text(f"Web server is already running. You can view the data at: {public_url}")
        return

    web_server_thread = threading.Thread(target=flask_app.run, kwargs={"port": 5001, "host": "0.0.0.0"})
    web_server_thread.daemon = True
    web_server_thread.start()
    bot_data["web_server_thread"] = web_server_thread

    try:
        public_url = ngrok.connect(5001)
        bot_data["public_url"] = public_url.public_url
        logger.info(f"ngrok tunnel opened at: {public_url}")
        await update.effective_message.reply_text(f"Web server started. You can view the data at: {bot_data['public_url']}")
    except Exception as e:
        logger.error(f"Error starting ngrok: {e}")
        await update.effective_message.reply_text("Could not start the web view. Please check the logs and ensure ngrok is configured.")

async def stop_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops the web server and ngrok tunnel."""
    public_url = bot_data.get("public_url")
    if public_url:
        ngrok.disconnect(public_url)
        logger.info("ngrok tunnel disconnected.")
        bot_data["public_url"] = None
        bot_data["web_server_thread"] = None
        await update.effective_message.reply_text("Web view stopped.")
    else:
        await update.effective_message.reply_text("Web view is not running.")


def main() -> None:
    """Start the bot."""
    database.initialize_database()

    ngrok_auth_token = os.getenv("NGROK_AUTHTOKEN")
    if ngrok_auth_token:
        ngrok.set_auth_token(ngrok_auth_token)

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

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_token", set_token))
    application.add_handler(CommandHandler("set_env_id", set_env_id))
    application.add_handler(CommandHandler("set_mailbox_id", set_mailbox_id))
    application.add_handler(CommandHandler("set_from_email", set_from_email))
    application.add_handler(CommandHandler("view_config", view_config))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("view_data", view_data))
    application.add_handler(CommandHandler("stop_view", stop_view))

    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^(fetch_all|fetch_email|stop_fetching|status|view_config|view_data)$"))
    application.add_handler(CallbackQueryHandler(set_fetching_mode_and_start, pattern="^mode_"))

    application.run_polling()


if __name__ == "__main__":
    main()
