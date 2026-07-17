"""Conversation domain events."""
def build_conversation_created_event(conversation_id: str, tenant_id: str, lead_id: str = None, channel: str = None) -> dict:
    return {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "channel": channel,
    }


def build_message_added_event(message_id: str, conversation_id: str, tenant_id: str, role: str, channel: str = None) -> dict:
    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "role": role,
        "channel": channel,
    }


def build_analysis_requested_event(conversation_id: str, tenant_id: str, audio_path: str = None, transcript: str = None) -> dict:
    return {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "audio_path": audio_path,
        "transcript": transcript,
    }


def build_analysis_completed_event(conversation_id: str, tenant_id: str, status: str, lead_score: dict = None, summary: str = None) -> dict:
    return {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "status": status,
        "lead_score": lead_score,
        "summary": summary,
    }
