from flask import Flask, render_template_string, jsonify
import database
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Saved Conversations</title>
    <style>
        body { font-family: sans-serif; margin: 2em; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .container { max-width: 1200px; margin: auto; }
        .no-data { text-align: center; color: #888; margin-top: 2em; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Saved Conversations</h1>
        {% if conversations %}
            <table>
                <thead>
                    <tr>
                        <th>Conversation ID</th>
                        <th>Email</th>
                        <th>Channel ID</th>
                        <th>Saved At</th>
                    </tr>
                </thead>
                <tbody>
                    {% for conv in conversations %}
                    <tr>
                        <td>{{ conv.conversation_id }}</td>
                        <td>{{ conv.email or 'N/A' }}</td>
                        <td>{{ conv.channel_id or 'N/A' }}</td>
                        <td>{{ conv.created_at }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p class="no-data">No conversations found in the database.</p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Renders a page showing all saved conversations."""
    try:
        logger.info("Fetching conversations for web view.")
        conversations = database.get_all_conversations()
        logger.info(f"Found {len(conversations)} conversations to render.")
        return render_template_string(HTML_TEMPLATE, conversations=conversations)
    except Exception as e:
        logger.error(f"Error rendering web view: {e}", exc_info=True)
        return "An error occurred while trying to render the page. Please check the logs.", 500

@app.route('/health')
def health_check():
    """A simple health check endpoint."""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(port=5001)
