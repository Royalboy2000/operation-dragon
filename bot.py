import logging
import os
import threading
import time
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

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
from task_manager import task_manager

# Conversation states for starting a task
SELECTING_TASK, CONFIGURING_TASK_CHANNEL, CONFIGURING_TASK_MESSAGE, CONFIGURING_TASK_EMAIL_SUBJECT, CONFIGURING_TASK_EMAIL_BODY = range(5)


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
    "web_server_thread": None,
    "public_url": None,
    "new_conversation_queue": queue.Queue(),
}

executor_fetch = ThreadPoolExecutor(max_workers=100)
executor_send_message = ThreadPoolExecutor(max_workers=200)
executor_send_email = ThreadPoolExecutor(max_workers=200)


# --- Worker Functions for Tasks ---

def _process_and_save_conversation(conv, fetch_channel):
    conv_id = conv.get("conversationId")
    email = conv.get("contact", {}).get("email")
    channel_id = conv.get("channelId")
    if fetch_channel is None and channel_id == "email":
        return False
    return database.add_conversation(conv_id, email, channel_id)

def fetch_page(page, channel):
    try:
        token = bot_data.get("api_token")
        env_id = bot_data.get("env_id")
        if not token or not env_id: return 0
        data = api_client.search_conversations(token, env_id, page=page, channel=channel)
        conversations = data.get("data", {}).get("searchConversations", [])
        if not conversations: return 0

        saved_count = 0
        for conv in conversations:
            if _process_and_save_conversation(conv, channel):
                saved_count += 1

        return len(conversations), saved_count
    except Exception as e:
        logger.error(f"Error fetching page {page}: {e}")
        return -1, 0

def scrape_all_pages_worker(stop_event, channel):
    page = 1
    while not stop_event.is_set():
        try:
            fetched_count, _ = fetch_page(page, channel)
            if fetched_count < 100:
                logger.info("Scrape complete: last page reached.")
                break
            page += 1
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error in scraping worker: {e}")
            break

def monitor_and_queue_worker(stop_event, channel):
    """Monitors page 1 and puts new, unique conversations into a queue."""
    while not stop_event.is_set():
        try:
            token = bot_data.get("api_token")
            env_id = bot_data.get("env_id")
            if not token or not env_id:
                time.sleep(10)
                continue

            data = api_client.search_conversations(token, env_id, page=1, channel=channel)
            conversations = data.get("data", {}).get("searchConversations", [])

            for conv in conversations:
                if _process_and_save_conversation(conv, channel):
                    bot_data["new_conversation_queue"].put(conv)
                    logger.info(f"New conversation found and queued: {conv.get('conversationId')}")

        except Exception as e:
            logger.error(f"Error in monitor worker: {e}")
        time.sleep(10)

def broadcast_worker(stop_event, message, is_email):
    """Periodically sends a message/email to all users in the database."""
    while not stop_event.is_set():
        logger.info(f"Starting a new broadcast cycle for {'email' if is_email else 'message'}.")
        all_convs = database.get_all_conversations()

        if is_email:
            email_convs = [c for c in all_convs if c.get("email") and "zenka.co.ke" not in c.get("email")]
            futures = [executor_send_email.submit(api_client.send_email, bot_data.get("api_token"), bot_data.get("env_id"), bot_data.get("mailbox_id"), c["conversation_id"], bot_data.get("from_email"), c["email"], message["subject"], message["body"]) for c in email_convs]
        else:
            futures = [executor_send_message.submit(api_client.send_text_message, bot_data.get("api_token"), bot_data.get("env_id"), c["conversation_id"], message) for c in all_convs]

        for future in as_completed(futures):
            future.result()

        logger.info("Broadcast cycle finished.")
        time.sleep(3600) # Loop every hour, for example

def send_to_new_worker(stop_event, message, is_email):
    """Consumes from the new conversation queue and sends a message/email."""
    while not stop_event.is_set():
        try:
            conv = bot_data["new_conversation_queue"].get(timeout=5)

            if is_email:
                if conv.get("contact", {}).get("email"):
                    executor_send_email.submit(api_client.send_email, bot_data.get("api_token"), bot_data.get("env_id"), bot_data.get("mailbox_id"), conv["conversationId"], bot_data.get("from_email"), conv["contact"]["email"], message["subject"], message["body"])
            else:
                executor_send_message.submit(api_client.send_text_message, bot_data.get("api_token"), bot_data.get("env_id"), conv["conversationId"], message)

            bot_data["new_conversation_queue"].task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error in send_to_new worker: {e}")

# ... (Telegram command handlers will be refactored to use the task manager)

def main():
    # ... (main function to set up and run the bot)
    pass

if __name__ == "__main__":
    main()
