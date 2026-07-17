"""Calendar service delegating to Google Calendar or Outlook Calendar APIs."""
from typing import Any, Dict, List, Optional
import httpx
from mcp.base.exceptions import ConnectorError, ExecutionError
from mcp.gmail.auth import GmailAuth
from mcp.outlook.auth import OutlookAuth


class CalendarService:
    """Standardizes operations across Google Calendar and MS Outlook Calendar."""

    def __init__(self, google_auth: Optional[GmailAuth] = None, outlook_auth: Optional[OutlookAuth] = None) -> None:
        self.google_auth = google_auth
        self.outlook_auth = outlook_auth

    async def _get_google_headers(self) -> Dict[str, str]:
        if not self.google_auth:
            raise ConnectorError("Google Calendar auth credentials not configured.")
        token = await self.google_auth.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _get_outlook_headers(self) -> Dict[str, str]:
        if not self.outlook_auth:
            raise ConnectorError("Outlook Calendar auth credentials not configured.")
        token = await self.outlook_auth.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def create_event(
        self,
        provider: str,
        subject: str,
        body: str,
        start_time: str,
        end_time: str,
        time_zone: str = "UTC",
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Creates an event on the specified calendar provider."""
        provider = provider.lower()
        if provider == "google":
            url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            headers = await self._get_google_headers()
            
            attendee_list = [{"email": email} for email in attendees] if attendees else []
            payload = {
                "summary": subject,
                "description": body,
                "start": {"dateTime": start_time, "timeZone": time_zone},
                "end": {"dateTime": end_time, "timeZone": time_zone},
                "attendees": attendee_list,
            }
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(url, json=payload, headers=headers)
                if res.status_code not in (200, 201):
                    raise ConnectorError(f"Google Calendar create_event failed ({res.status_code}): {res.text}")
                return res.json()
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Google Calendar create_event error: {e}") from e
                
        elif provider == "outlook":
            url = "https://graph.microsoft.com/v1.0/me/events"
            headers = await self._get_outlook_headers()
            
            attendee_list = []
            if attendees:
                for email in attendees:
                    attendee_list.append({
                        "emailAddress": {"address": email, "name": email},
                        "type": "required"
                    })
                    
            payload = {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "start": {"dateTime": start_time, "timeZone": time_zone},
                "end": {"dateTime": end_time, "timeZone": time_zone},
                "attendees": attendee_list,
            }
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(url, json=payload, headers=headers)
                if res.status_code not in (200, 201):
                    raise ConnectorError(f"Outlook Calendar create_event failed ({res.status_code}): {res.text}")
                return res.json()
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Outlook Calendar create_event error: {e}") from e
        else:
            raise ValueError(f"Unknown calendar provider: {provider}")

    async def update_event(
        self, provider: str, event_id: str, event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Updates an existing calendar event."""
        provider = provider.lower()
        if provider == "google":
            url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}"
            headers = await self._get_google_headers()
            
            # Convert fields if needed
            payload = {}
            for k, v in event_data.items():
                if k == "subject":
                    payload["summary"] = v
                elif k == "body":
                    payload["description"] = v
                elif k == "start_time":
                    payload["start"] = {"dateTime": v}
                elif k == "end_time":
                    payload["end"] = {"dateTime": v}
                else:
                    payload[k] = v
                    
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.patch(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise ConnectorError(f"Google Calendar update_event failed ({res.status_code}): {res.text}")
                return res.json()
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Google Calendar update_event error: {e}") from e
                
        elif provider == "outlook":
            url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}"
            headers = await self._get_outlook_headers()
            
            payload = {}
            for k, v in event_data.items():
                if k == "subject":
                    payload["subject"] = v
                elif k == "body":
                    payload["body"] = {"contentType": "Text", "content": v}
                elif k == "start_time":
                    payload["start"] = {"dateTime": v}
                elif k == "end_time":
                    payload["end"] = {"dateTime": v}
                else:
                    payload[k] = v
                    
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.patch(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise ConnectorError(f"Outlook Calendar update_event failed ({res.status_code}): {res.text}")
                return res.json()
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Outlook Calendar update_event error: {e}") from e
        else:
            raise ValueError(f"Unknown calendar provider: {provider}")

    async def cancel_event(self, provider: str, event_id: str) -> Dict[str, Any]:
        """Cancels/deletes a calendar event."""
        provider = provider.lower()
        if provider == "google":
            url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}"
            headers = await self._get_google_headers()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.delete(url, headers=headers)
                if res.status_code not in (200, 204):
                    raise ConnectorError(f"Google Calendar cancel_event failed ({res.status_code}): {res.text}")
                return {"status": "success", "event_id": event_id}
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Google Calendar cancel_event error: {e}") from e
                
        elif provider == "outlook":
            url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}"
            headers = await self._get_outlook_headers()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.delete(url, headers=headers)
                if res.status_code not in (200, 204):
                    raise ConnectorError(f"Outlook Calendar cancel_event failed ({res.status_code}): {res.text}")
                return {"status": "success", "event_id": event_id}
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Outlook Calendar cancel_event error: {e}") from e
        else:
            raise ValueError(f"Unknown calendar provider: {provider}")

    async def get_availability(
        self,
        provider: str,
        start_time: str,
        end_time: str,
        emails: List[str],
        time_zone: str = "UTC",
    ) -> Dict[str, Any]:
        """Queries calendar schedules/availability slots."""
        provider = provider.lower()
        if provider == "google":
            url = "https://www.googleapis.com/calendar/v3/freeBusy"
            headers = await self._get_google_headers()
            payload = {
                "timeMin": start_time,
                "timeMax": end_time,
                "timeZone": time_zone,
                "items": [{"id": email} for email in emails],
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise ConnectorError(f"Google Calendar freeBusy failed ({res.status_code}): {res.text}")
                return res.json()
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Google Calendar freeBusy error: {e}") from e
                
        elif provider == "outlook":
            url = "https://graph.microsoft.com/v1.0/me/calendar/getSchedule"
            headers = await self._get_outlook_headers()
            payload = {
                "schedules": emails,
                "startTime": {"dateTime": start_time, "timeZone": time_zone},
                "endTime": {"dateTime": end_time, "timeZone": time_zone},
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise ConnectorError(f"Outlook Calendar getSchedule failed ({res.status_code}): {res.text}")
                return res.json()
            except Exception as e:
                if isinstance(e, ConnectorError):
                    raise
                raise ExecutionError(f"Outlook Calendar getSchedule error: {e}") from e
        else:
            raise ValueError(f"Unknown calendar provider: {provider}")
