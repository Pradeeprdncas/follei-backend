"""Email Provider - Brevo (formerly Sendinblue) integration."""
from typing import Dict, Any, List, Optional
from pathlib import Path
from loguru import logger
import httpx
from app.config.settings import get_settings

_settings = get_settings()


class EmailProvider:
    """Brevo email provider for sending transactional and campaign emails.
    
    Uses Brevo API v3.
    """
    
    def __init__(self):
        """Initialize Brevo email provider."""
        self.api_key = _settings.BREVO_API_KEY
        self.base_url = "https://api.brevo.com/v3"
        self.sender_email = _settings.BREVO_SENDER_EMAIL or "noreply@yourdomain.com"
        self.sender_name = _settings.BREVO_SENDER_NAME or "Your Company"
        
        if not self.api_key:
            logger.warning("BREVO_API_KEY not configured. Email sending will fail.")

    async def send(self, recipient: str, subject: str | None,
                   body: str, image_url: str | None = None) -> dict:
        return await self.send_email(
            to_email=recipient,
            to_name="Valued Customer",
            subject=subject or "",
            body=body,
            html_body=body,
        )

    async def send_bulk(self, recipients: list[dict], subject: str | None,
                        body: str, image_url: str | None = None) -> dict:
        formatted = [{"email": r["recipient"], "name": r.get("name", "Valued Customer")} for r in recipients]
        return await self.send_bulk_email(formatted, subject or "", body, body)
    
    async def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a single email.
        
        Args:
            to_email: Recipient email
            to_name: Recipient name
            subject: Email subject
            body: Plain text body
            html_body: HTML body (optional)
            reply_to: Reply-to email (optional)
            
        Returns:
            Response with message_id and status
        """
        if not self.api_key:
            return {"success": False, "error": "Brevo API key not configured"}
        
        try:
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
            
            payload = {
                "sender": {
                    "email": self.sender_email,
                    "name": self.sender_name,
                },
                "to": [
                    {
                        "email": to_email,
                        "name": to_name,
                    }
                ],
                "subject": subject,
                "textContent": body,
            }
            
            if html_body:
                payload["htmlContent"] = html_body
            
            if reply_to:
                payload["replyTo"] = {"email": reply_to}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/smtp/email",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                
                if response.status_code in (200, 201):
                    result = response.json()
                    logger.info(f"Email sent to {to_email}: {result.get('messageId')}")
                    return {
                        "success": True,
                        "message_id": result.get("messageId"),
                        "status": "sent",
                    }
                else:
                    error_msg = f"Brevo API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
                    
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_bulk_email(
        self,
        recipients: List[Dict[str, str]],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send bulk emails to multiple recipients.
        
        Args:
            recipients: List of {"email": "...", "name": "..."}
            subject: Email subject
            body: Plain text body
            html_body: HTML body (optional)
            
        Returns:
            Response with message_id and stats
        """
        if not self.api_key:
            return {"success": False, "error": "Brevo API key not configured"}
        
        try:
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
            
            # Batch recipients (Brevo limit: 1000 per request)
            batch_size = 1000
            results = []
            
            for i in range(0, len(recipients), batch_size):
                batch = recipients[i:i + batch_size]
                
                payload = {
                    "sender": {
                        "email": self.sender_email,
                        "name": self.sender_name,
                    },
                    "to": batch,
                    "subject": subject,
                    "textContent": body,
                }
                
                if html_body:
                    payload["htmlContent"] = html_body
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.base_url}/smtp/email",
                        headers=headers,
                        json=payload,
                        timeout=60.0,
                    )
                    
                    if response.status_code in (200, 201):
                        result = response.json()
                        results.append({
                            "success": True,
                            "message_id": result.get("messageId"),
                            "batch": i // batch_size + 1,
                        })
                    else:
                        error_msg = f"Brevo API error: {response.status_code} - {response.text}"
                        logger.error(error_msg)
                        results.append({
                            "success": False,
                            "error": error_msg,
                            "batch": i // batch_size + 1,
                        })
            
            successful = sum(1 for r in results if r.get("success"))
            failed = len(results) - successful
            
            logger.info(f"Bulk email sent: {successful} successful, {failed} failed")
            
            return {
                "success": True,
                "total": len(recipients),
                "successful": successful,
                "failed": failed,
                "results": results,
            }
            
        except Exception as e:
            logger.error(f"Failed to send bulk email: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_email_stats(self, message_id: str) -> Dict[str, Any]:
        """Get email delivery stats (opens, clicks, etc.).
        
        Args:
            message_id: Brevo message ID
            
        Returns:
            Email statistics
        """
        if not self.api_key:
            return {"success": False, "error": "Brevo API key not configured"}
        
        try:
            headers = {
                "api-key": self.api_key,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/smtp/statistics/events",
                    headers=headers,
                    params={"messageId": message_id},
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "stats": response.json(),
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Brevo API error: {response.status_code}",
                    }
                    
        except Exception as e:
            logger.error(f"Failed to get email stats: {e}")
            return {"success": False, "error": str(e)}