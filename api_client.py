import requests

API_URL = "https://api-inbox.chatbotize.com/graphql"

def search_conversations(token, environment_id, channel=None):
    """
    Searches for conversations, with an optional filter for the channel.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    query = """
    query SearchConversations($page: Int!, $entriesPerPage: Int!, $environmentId: String!, $channelIdsFilter: [String!]!) {
      searchConversations(page: 1, entriesPerPage: 100, environmentId: $environmentId, channelIdsFilter: $channelIdsFilter) {
        conversationId
        contact {
          email
        }
      }
    }
    """
    variables = {
        "page": 1,
        "entriesPerPage": 100,
        "environmentId": environment_id,
        "channelIdsFilter": [channel] if channel else [],
    }
    json_data = {"query": query, "variables": variables}
    response = requests.post(API_URL, headers=headers, json=json_data)
    response.raise_for_status()
    return response.json()

def send_text_message(token, environment_id, conversation_id, text):
    """
    Sends a text message to a conversation.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    query = """
    mutation SendText($environmentId: String!, $conversationId: String!, $text: String!) {
      sendText(environmentId: $environmentId, conversationId: $conversationId, text: $text) {
        ... on Event {
          id
        }
      }
    }
    """
    variables = {
        "environmentId": environment_id,
        "conversationId": conversation_id,
        "text": text,
    }
    json_data = {"query": query, "variables": variables}
    response = requests.post(API_URL, headers=headers, json=json_data)
    response.raise_for_status()
    return response.json()

def send_email(token, environment_id, mailbox_id, conversation_id, from_email, to_email, subject, body):
    """
    Sends an email to a conversation.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    query = """
    mutation SendEmail($environmentId: String!, $conversationId: String!, $email: EmailInput!, $mailboxId: String!) {
      sendEmail(environmentId: $environmentId, conversationId: $conversationId, email: $email, mailboxId: $mailboxId, startConversation: false) {
        ... on SendEmailResult {
          event {
            id
          }
        }
      }
    }
    """
    email_variable = {
        "from": {"email": from_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "messageContentHtml": body,
        "cc": [],
        "bcc": [],
        "replyTo": [],
        "attachmentFileIds": [],
    }
    variables = {
        "environmentId": environment_id,
        "conversationId": conversation_id,
        "email": email_variable,
        "mailboxId": mailbox_id,
    }
    json_data = {"query": query, "variables": variables}
    response = requests.post(API_URL, headers=headers, json=json_data)
    response.raise_for_status()
    return response.json()
