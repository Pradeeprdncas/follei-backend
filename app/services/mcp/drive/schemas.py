"""Google Drive tool parameter schemas."""

LIST_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "page_size": {"type": "integer", "description": "Max number of files to return", "default": 20}
    },
}

SEARCH_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Drive query term (e.g. name contains 'project' or mimeType = 'application/pdf')",
        }
    },
    "required": ["query"],
}

READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "description": "The unique Google Drive ID of the file to read"}
    },
    "required": ["file_id"],
}

DOWNLOAD_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "description": "The Google Drive ID of the file to download"}
    },
    "required": ["file_id"],
}

UPLOAD_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "The target name of the file to upload"},
        "content": {"type": "string", "description": "Text/string content of the file"},
        "mime_type": {"type": "string", "description": "MIME type (e.g. text/plain)", "default": "text/plain"},
        "parent_id": {"type": "string", "description": "Optional parent folder ID to upload into"},
    },
    "required": ["name", "content"],
}

CREATE_FOLDER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "The name of the folder to create"},
        "parent_id": {"type": "string", "description": "Optional parent folder ID to create inside"},
    },
    "required": ["name"],
}

MOVE_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "description": "The Google Drive ID of the file to move"},
        "add_parents": {"type": "string", "description": "Comma-separated folder IDs to add"},
        "remove_parents": {"type": "string", "description": "Comma-separated folder IDs to remove"},
    },
    "required": ["file_id", "add_parents", "remove_parents"],
}

DELETE_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "description": "The Google Drive ID of the file to delete/trash"},
        "trash": {"type": "boolean", "description": "Trash if True, delete permanently if False", "default": True},
    },
    "required": ["file_id"],
}

SHARE_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "description": "The Google Drive ID of the file to share"},
        "email_address": {"type": "string", "description": "Target email address to share with"},
        "role": {"type": "string", "description": "Role (e.g. owner, organizer, writer, commenter, reader)"},
        "type": {"type": "string", "description": "Type of permission (e.g. user, group, domain, anyone)"},
    },
    "required": ["file_id", "email_address", "role", "type"],
}

GET_PERMISSIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "description": "The Google Drive ID of the file to get permissions list"}
    },
    "required": ["file_id"],
}
