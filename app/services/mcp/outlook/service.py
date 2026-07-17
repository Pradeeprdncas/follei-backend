"""Microsoft Graph Outlook API service integration wrapper."""
from typing import Any, Dict, List, Optional
import httpx
from mcp.base.exceptions import ConnectorError, ExecutionError
from mcp.outlook.auth import OutlookAuth


class OutlookService:
    """Wrapper for calling Microsoft Graph REST endpoints using HTTPX."""

    def __init__(self, auth: OutlookAuth) -> None:
        self.auth = auth
        self.base_url = "https://graph.microsoft.com/v1.0"

    async def _get_headers(self) -> Dict[str, str]:
        access_token = await self.auth.get_valid_token()
        headers = self.auth.get_auth_headers()
        headers["Content-Type"] = "application/json"
        return headers

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Sends an email using Microsoft Graph sendMail endpoint."""
        headers = await self._get_headers()
        
        # Build recipients
        to_recipients = [{"emailAddress": {"address": to}}]
        cc_recipients = [{"emailAddress": {"address": email}} for email in cc] if cc else []
        bcc_recipients = [{"emailAddress": {"address": email}} for email in bcc] if bcc else []
        
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": to_recipients,
                "ccRecipients": cc_recipients,
                "bccRecipients": bcc_recipients,
            },
            "saveToSentItems": "true",
        }
        
        url = f"{self.base_url}/me/sendMail"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
            # sendMail returns 202 Accepted on success with no body
            if response.status_code not in (200, 202):
                raise ConnectorError(
                    f"Outlook send_email failed ({response.status_code}): {response.text}"
                )
            return {"status": "success", "message": "Email sent"}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to send Outlook email: {e}") from e

    async def reply_email(self, message_id: str, body: str) -> Dict[str, Any]:
        """Replies to a message by creating a reply draft, updating it, and sending it."""
        headers = await self._get_headers()
        
        # 1. Create a reply draft
        create_draft_url = f"{self.base_url}/me/messages/{message_id}/createReply"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(create_draft_url, json={}, headers=headers)
                
            if response.status_code not in (200, 201):
                raise ConnectorError(
                    f"Outlook createReply draft failed ({response.status_code}): {response.text}"
                )
                
            draft_message = response.json()
            draft_id = draft_message["id"]
            
            # 2. Update the draft with the body content
            update_draft_url = f"{self.base_url}/me/messages/{draft_id}"
            update_payload = {"body": {"contentType": "Text", "content": body}}
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                update_response = await client.patch(
                    update_draft_url, json=update_payload, headers=headers
                )
                
            if update_response.status_code != 200:
                raise ConnectorError(
                    f"Outlook update draft failed ({update_response.status_code}): {update_response.text}"
                )
                
            # 3. Send the draft
            send_draft_url = f"{self.base_url}/me/messages/{draft_id}/send"
            async with httpx.AsyncClient(timeout=15.0) as client:
                send_response = await client.post(send_draft_url, json={}, headers=headers)
                
            if send_response.status_code not in (200, 202):
                raise ConnectorError(
                    f"Outlook send draft failed ({send_response.status_code}): {send_response.text}"
                )
                
            return {"status": "success", "draft_id": draft_id}
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to reply to Outlook email: {e}") from e

    async def read_email(self, message_id: str) -> Dict[str, Any]:
        """Retrieves details of a specific email message."""
        headers = await self._get_headers()
        url = f"{self.base_url}/me/messages/{message_id}"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                
            if response.status_code != 200:
                raise ConnectorError(
                    f"Outlook read_email failed ({response.status_code}): {response.text}"
                )
            return response.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to read Outlook email: {e}") from e

    async def create_event(
        self,
        subject: str,
        body: str,
        start_time: str,
        end_time: str,
        time_zone: str = "UTC",
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Creates a Calendar Event in Outlook Calendar."""
        headers = await self._get_headers()
        
        attendee_list = []
        if attendees:
            for email in attendees:
                attendee_list.append(
                    {
                        "emailAddress": {"address": email, "name": email},
                        "type": "required",
                    }
                )
                
        payload = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "start": {"dateTime": start_time, "timeZone": time_zone},
            "end": {"dateTime": end_time, "timeZone": time_zone},
            "attendees": attendee_list,
        }
        
        url = f"{self.base_url}/me/events"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
            if response.status_code not in (200, 201):
                raise ConnectorError(
                    f"Outlook create_event failed ({response.status_code}): {response.text}"
                )
            return response.json()
        except Exception as e:
            if isinstance(e, ConnectorError):
                raise
            raise ExecutionError(f"Failed to create Outlook calendar event: {e}") from e
