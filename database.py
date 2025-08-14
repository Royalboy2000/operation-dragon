import sqlite3
import logging
import threading

DATABASE_NAME = "conversations.db"
db_lock = threading.Lock()

def get_db_connection():
    """Creates a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Initializes the database and creates the conversations table if it doesn't exist."""
    with db_lock:
        conn = get_db_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL UNIQUE,
                    email TEXT,
                    channel_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email ON conversations (email)")
            conn.commit()
            logging.info("Database initialized successfully.")
        except Exception as e:
            logging.error(f"Error initializing database: {e}")
        finally:
            conn.close()

def clear_conversations():
    """Clears all conversations from the database."""
    with db_lock:
        conn = get_db_connection()
        try:
            conn.execute("DELETE FROM conversations")
            conn.commit()
            logging.info("Cleared all conversations from the database.")
        except Exception as e:
            logging.error(f"Error clearing conversations: {e}")
        finally:
            conn.close()

def add_conversation(conversation_id, email, channel_id):
    """
    Adds a new conversation to the database in a thread-safe manner.
    - Ignores conversations with emails that are already in the database.
    - Returns True if the conversation was added, False otherwise.
    """
    with db_lock:
        conn = get_db_connection()
        try:
            if email:
                cursor = conn.execute("SELECT id FROM conversations WHERE email = ?", (email,))
                if cursor.fetchone():
                    return False

            conn.execute(
                "INSERT INTO conversations (conversation_id, email, channel_id) VALUES (?, ?, ?)",
                (conversation_id, email, channel_id)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logging.error(f"Error adding conversation {conversation_id}: {e}")
            return False
        finally:
            conn.close()

def get_all_conversations():
    """Retrieves all conversations from the database."""
    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.execute("SELECT conversation_id, email, channel_id, created_at FROM conversations ORDER BY created_at DESC")
            conversations = cursor.fetchall()
            return [dict(row) for row in conversations]
        except Exception as e:
            logging.error(f"Error getting all conversations: {e}")
            return []
        finally:
            conn.close()
