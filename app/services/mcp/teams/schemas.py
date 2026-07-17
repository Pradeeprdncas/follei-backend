"""Microsoft Teams tool parameter schemas."""

SEND_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "The text content of the message to send"},
        "chat_id": {"type": "string", "description": "ID of the target chat conversation (if sending to chat)"},
        "channel_id": {"type": "string", "description": "ID of the target channel (if sending to channel)"},
        "team_id": {"type": "string", "description": "ID of the team (required if sending to channel)"},
    },
    "required": ["text"],
}

LIST_TEAMS_SCHEMA = {
    "type": "object",
    "properties": {},
}

LIST_CHANNELS_SCHEMA = {
    "type": "object",
    "properties": {
        "team_id": {"type": "string", "description": "The unique ID of the Team (e.g. team-123)"}
    },
    "required": ["team_id"],
}

GET_MESSAGES_SCHEMA = {
    "type": "object",
    "properties": {
        "chat_id": {"type": "string", "description": "ID of the chat conversation"},
        "channel_id": {"type": "string", "description": "ID of the channel"},
        "team_id": {"type": "string", "description": "ID of the team (required if fetching from channel)"},
        "limit": {"type": "integer", "description": "Max number of messages to fetch", "default": 20},
    },
}

CREATE_CHANNEL_SCHEMA = {
    "type": "object",
    "properties": {
        "team_id": {"type": "string", "description": "The ID of the team to create channel inside"},
        "name": {"type": "string", "description": "The display name of the channel"},
        "description": {"type": "string", "description": "A description of the channel"},
    },
    "required": ["team_id", "name"],
}

ADD_MEMBER_SCHEMA = {
    "type": "object",
    "properties": {
        "team_id": {"type": "string", "description": "The target Team ID"},
        "user_id": {"type": "string", "description": "The Graph user ID or email of user to add"},
        "roles": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of roles (e.g. owner or empty for member)",
            "default": [],
        },
    },
    "required": ["team_id", "user_id"],
}

SCHEDULE_MEETING_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "The subject/topic of the online meeting"},
        "start_time": {"type": "string", "description": "ISO 8601 start time (e.g. 2026-06-15T15:00:00Z)"},
        "end_time": {"type": "string", "description": "ISO 8601 end time (e.g. 2026-06-15T16:00:00Z)"},
    },
    "required": ["subject", "start_time", "end_time"],
}
