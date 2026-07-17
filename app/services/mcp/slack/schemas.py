"""Slack tool parameter schemas."""

SEND_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "The channel ID or name (e.g. C12345 or #general)"},
        "text": {"type": "string", "description": "The message text to send"},
    },
    "required": ["channel", "text"],
}

LIST_CHANNELS_SCHEMA = {
    "type": "object",
    "properties": {
        "types": {
            "type": "string",
            "description": "Public or private channels (comma-separated, e.g. public_channel,private_channel)",
            "default": "public_channel",
        }
    },
}

GET_CHANNEL_MESSAGES_SCHEMA = {
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "The channel ID (e.g. C12345)"},
        "limit": {"type": "integer", "description": "Max number of messages to fetch", "default": 20},
    },
    "required": ["channel"],
}

CREATE_CHANNEL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "The name of the channel to create"},
        "is_private": {"type": "boolean", "description": "Whether to make it private", "default": False},
    },
    "required": ["name"],
}

INVITE_USER_SCHEMA = {
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "The channel ID to invite the user to"},
        "user_id": {"type": "string", "description": "The ID of the user (e.g. U12345)"},
    },
    "required": ["channel", "user_id"],
}

GET_USER_INFO_SCHEMA = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "description": "The Slack user ID (e.g. U12345)"}
    },
    "required": ["user_id"],
}

SEARCH_MESSAGES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query (e.g. error, from:alice)"}
    },
    "required": ["query"],
}

UPLOAD_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "channels": {"type": "string", "description": "Comma-separated list of channel IDs to share file in"},
        "content": {"type": "string", "description": "String content of the file"},
        "filename": {"type": "string", "description": "Name of the file to create"},
    },
    "required": ["channels", "content", "filename"],
}

SCHEDULE_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "The channel ID or name"},
        "text": {"type": "string", "description": "The message text to send"},
        "post_at": {"type": "number", "description": "Unix timestamp in seconds when the message should post"},
    },
    "required": ["channel", "text", "post_at"],
}
