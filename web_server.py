from flask import Flask, render_template, jsonify
import database
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    """Renders a page showing all saved conversations."""
    try:
        logger.info("Fetching conversations for web view.")
        conversations = database.get_all_conversations()
        logger.info(f"Found {len(conversations)} conversations to render.")
        return render_template("index.html", conversations=conversations)
    except Exception as e:
        logger.error(f"Error rendering web view: {e}", exc_info=True)
        return "An error occurred while trying to render the page. Please check the logs.", 500

@app.route('/health')
def health_check():
    """A simple health check endpoint."""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(port=5001)
