"""Gmail API REST service integration wrapper."""
import base64
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger
from mcp.base.exceptions import ConnectorError, ExecutionError
from mcp.gmail.auth import GmailAuth


class GmailService:
    """Wrapper for calling Google Gmail REST endpoints using HTTPX and GmailAuth."""

    def __init__(self, auth: GmailAuth) -> None:
        self.auth = auth
        self.base_url = "https://gmail.googleapis.com/gmail/v1/users/me"

    async def _get_headers(self) -> Dict[str, str]:
        access_token = await self.auth.get_valid_token()
        headers = self.auth.get_auth_headers()
        headers["Content-Type"] = "application/json"
        return headers

    def _create_mime_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> str:
        """Constructs a MIME email message and returns base64url-encoded string."""
        message = MIMEText(body, "plain", "utf-8")
        message["to"] = to
        message["from"] = "me"
        message["subject"] = subject
        
        if cc:
            message["cc"] = ", ".join(cc)
        if bcc:
            message["bcc"] = ", ".join(bcc)
            
        if thread_id:
            # Threading headers
            if in_reply_to:
                message["In-Reply-To"] = in_reply_to
            if references:
                message["References"] = references

        raw_bytes = message.as_bytes()
        encoded = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
        return encoded

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Sends a new email message using the Gmail API."""
        headers = await self._get_headers()
        raw_mime = self._create_mime_message(to, subject, body, cc, bcc)
        
        url = f"{self.base_url}/messages/send"
        payload = {"raw": raw_mime}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
            if response.status_code != 200:
                raise ConnectorError(
                    f"Gmail send_email failed ({response.status_code}): {response.text}"
                )
            return response.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to send email: {e}") from e

    async def reply_email(self, thread_id: str, body: str) -> Dict[str, Any]:
        """Replies to an existing email thread by retrieving the thread context first."""
        headers = await self._get_headers()
        
        # 1. Fetch thread to read last message details (subject, message-id) for correct threading
        thread_data = await self.read_thread(thread_id)
        messages = thread_data.get("messages", [])
        if not messages:
            raise ConnectorError(f"Thread '{thread_id}' contains no messages to reply to.")
            
        last_message = messages[-1]
        
        # Retrieve subject and message ID headers
        headers_list = last_message.get("payload", {}).get("headers", [])
        subject = "Re: Subject"
        message_id = None
        to_email = None
        
        for h in headers_list:
            name = h.get("name", "").lower()
            if name == "subject":
                subject = h.get("value", "")
                if not subject.lower().startswith("re:"):
                    subject = f"Re: {subject}"
            elif name == "message-id":
                message_id = h.get("value", "")
            elif name == "from":
                to_email = h.get("value", "")
                
        if not to_email:
            raise ConnectorError(f"Could not determine reply recipient from last message in thread {thread_id}")

        # 2. Build MIME email with threading headers
        raw_mime = self._create_mime_message(
            to=to_email,
            subject=subject,
            body=body,
            thread_id=thread_id,
            in_reply_to=message_id,
            references=message_id,
        )
        
        url = f"{self.base_url}/messages/send"
        payload = {"raw": raw_mime, "threadId": thread_id}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
            if response.status_code != 200:
                raise ConnectorError(
                    f"Gmail reply failed ({response.status_code}): {response.text}"
                )
            return response.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to reply to email: {e}") from e

    async def search_emails(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Searches user messages using Gmail search filters."""
        headers = await self._get_headers()
        url = f"{self.base_url}/messages"
        params = {"q": query, "maxResults": max_results}
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=headers)
                
            if response.status_code != 200:
                raise ConnectorError(
                    f"Gmail search failed ({response.status_code}): {response.text}"
                )
            data = response.json()
            return data.get("messages", [])
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to search emails: {e}") from e

    async def read_thread(self, thread_id: str) -> Dict[str, Any]:
        """Retrieves a full conversation thread by thread_id."""
        headers = await self._get_headers()
        url = f"{self.base_url}/threads/{thread_id}"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                
            if response.status_code != 200:
                raise ConnectorError(
                    f"Gmail read thread failed ({response.status_code}): {response.text}"
                )
            return response.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to read email thread: {e}") from e
