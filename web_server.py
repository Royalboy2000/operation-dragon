from flask import Flask, render_template_string
import database

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Saved Conversations</title>
    <style>
        body { font-family: sans-serif; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h1>Saved Conversations</h1>
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
</body>
</html>
"""

@app.route('/')
def index():
    """Renders a page showing all saved conversations."""
    conversations = database.get_all_conversations()
    return render_template_string(HTML_TEMPLATE, conversations=conversations)

if __name__ == '__main__':
    # The web server will be run by the bot, not as a standalone script.
    # This block is for potential testing.
    app.run(port=5001)
