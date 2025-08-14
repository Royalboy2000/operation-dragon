import requests

API_URL = "https://api-inbox.chatbotize.com/graphql"

def search_conversations(token, environment_id, page=1, channel=None):
    """
    Searches for conversations, with an optional filter for the channel.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    # This query is taken from the user-provided `grab_conversatiodID-EMAIL.txt`
    query = """
    query SearchConversations($page: Int!, $entriesPerPage: Int!, $environmentId: String!, $sortBy: ConversationsSortBy, $sortDirection: ConversationSortDirection, $textFilter: String, $clientFilter: String, $ticketIdFilter: String, $startFromFilter: Long, $startToFilter: Long, $lastMessageTimeFromFilter: Long, $lastMessageTimeToFilter: Long, $channelIdsFilter: [String!]!, $agentIdsFilter: [String!]!, $departmentIdsFilter: [String!]!, $quickFilter: String) {
      searchConversations(page: $page, entriesPerPage: $entriesPerPage, environmentId: $environmentId, sortBy: $sortBy, sortDirection: $sortDirection, textFilter: $textFilter, clientFilter: $clientFilter, ticketIdFilter: $ticketIdFilter, startFromFilter: $startFromFilter, startToFilter: $startToFilter, lastMessageTimeFromFilter: $lastMessageTimeFromFilter, lastMessageTimeToFilter: $lastMessageTimeToFilter, channelIdsFilter: $channelIdsFilter, agentIdsFilter: $agentIdsFilter, departmentIdsFilter: $departmentIdsFilter, quickFilter: $quickFilter) {
        conversationId
        channelId
        title
        contact {
          firstName
          lastName
          name
          email
          __typename
        }
        ticketId
        startTime
        lastMessageTime
        messagesCount
        agentIds {
          agentId
          firstName
          lastName
          email
          __typename
        }
        departments {
          id
          name
          __typename
        }
        __typename
      }
    }
    """
    variables = {
        "environmentId": environment_id,
        "page": page,
        "sortBy": "LAST_MESSAGE_TIME",
        "sortDirection": "DESC",
        "channelIdsFilter": [channel] if channel else [],
        "entriesPerPage": 100,
        "agentIdsFilter": [],
        "departmentIdsFilter": [],
    }
    json_data = {
        "operationName": "SearchConversations",
        "variables": variables,
        "query": query,
    }
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
    json_data = {"operationName": "SendText", "query": query, "variables": variables}
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
    mutation SendEmail($environmentId: String!, $conversationId: String!, $email: EmailInput!, $mailboxId: String!, $inReplyToMessageId: String, $startConversation: Boolean!, $delayMillis: Long) {
      sendEmail(environmentId: $environmentId, conversationId: $conversationId, email: $email, mailboxId: $mailboxId, inReplyToMessageId: $inReplyToMessageId, startConversation: $startConversation, delayMillis: $delayMillis) {
        interruptToken
        event {
          id
        }
        __typename
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
        "startConversation": False,
        "inReplyToMessageId": None,
        "delayMillis": None,
    }
    json_data = {"operationName": "SendEmail", "query": query, "variables": variables}
    response = requests.post(API_URL, headers=headers, json=json_data)
    response.raise_for_status()
    return response.json()
