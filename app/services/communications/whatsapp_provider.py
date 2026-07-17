"""WhatsApp Provider - Meta WhatsApp Business API integration."""
from typing import Dict, Any, List, Optional
from loguru import logger
import httpx
from app.config.settings import get_settings

_settings = get_settings()


class WhatsAppProvider:
    """Meta WhatsApp Business API provider.
    
    Uses WhatsApp Cloud API for sending/receiving messages.
    """
    
    def __init__(self):
        """Initialize WhatsApp provider."""
        self.api_token = _settings.WHATSAPP_API_TOKEN
        self.phone_number_id = _settings.WHATSAPP_PHONE_NUMBER_ID
        self.base_url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}"
        
        if not self.api_token or not self.phone_number_id:
            logger.warning("WhatsApp credentials not configured. WhatsApp sending will fail.")

    async def send(self, recipient: str, subject: str | None,
                   body: str, image_url: str | None = None) -> dict:
        if image_url:
            return await self.send_media(to_phone=recipient, media_url=image_url, caption=body)
        return await self.send_message(to_phone=recipient, message=body)

    async def send_bulk(self, recipients: list[dict], subject: str | None,
                        body: str, image_url: str | None = None) -> dict:
        results = []
        for r in recipients:
            result = await self.send(recipient=r["recipient"], subject=subject, body=body, image_url=image_url)
            results.append(result)
        successful = sum(1 for r in results if r.get("success"))
        return {"success": successful > 0, "total": len(recipients), "successful": successful, "results": results}
    
    async def send_message(
        self,
        to_phone: str,
        message: str,
        media_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a WhatsApp text message.
        
        Args:
            to_phone: Recipient phone number (with country code, e.g., +1234567890)
            message: Message text
            media_url: Optional media URL (image, document, etc.)
            
        Returns:
            Response with message_id and status
        """
        if not self.api_token or not self.phone_number_id:
            return {"success": False, "error": "WhatsApp not configured"}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
            
            # Format phone number (remove +, spaces, dashes)
            to_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_phone,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": message,
                },
            }
            
            # Add media if provided
            if media_url:
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_phone,
                    "type": "image",
                    "image": {
                        "link": media_url,
                    },
                }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                
                if response.status_code in (200, 201):
                    result = response.json()
                    message_id = result.get("messages", [{}])[0].get("id")
                    logger.info(f"WhatsApp message sent to {to_phone}: {message_id}")
                    return {
                        "success": True,
                        "message_id": message_id,
                        "status": "sent",
                    }
                else:
                    error_msg = f"WhatsApp API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
                    
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {to_phone}: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Send a WhatsApp template message.
        
        Args:
            to_phone: Recipient phone number
            template_name: Template name (must be approved by Meta)
            language_code: Language code (e.g., "en_US")
            components: Template components (parameters)
            
        Returns:
            Response with message_id and status
        """
        if not self.api_token or not self.phone_number_id:
            return {"success": False, "error": "WhatsApp not configured"}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
            
            # Format phone number
            to_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {
                        "code": language_code,
                    },
                },
            }
            
            # Add components if provided
            if components:
                payload["template"]["components"] = components
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                
                if response.status_code in (200, 201):
                    result = response.json()
                    message_id = result.get("messages", [{}])[0].get("id")
                    logger.info(f"WhatsApp template sent to {to_phone}: {message_id}")
                    return {
                        "success": True,
                        "message_id": message_id,
                        "status": "sent",
                    }
                else:
                    error_msg = f"WhatsApp API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
                    
        except Exception as e:
            logger.error(f"Failed to send WhatsApp template to {to_phone}: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_media(
        self,
        to_phone: str,
        media_url: str,
        media_type: str = "image",
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send WhatsApp media message.
        
        Args:
            to_phone: Recipient phone number
            media_url: URL of the media
            media_type: Type of media (image, document, audio, video)
            caption: Optional caption
            
        Returns:
            Response with message_id and status
        """
        if not self.api_token or not self.phone_number_id:
            return {"success": False, "error": "WhatsApp not configured"}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
            
            # Format phone number
            to_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_phone,
                "type": media_type,
                media_type: {
                    "link": media_url,
                },
            }
            
            # Add caption if provided
            if caption and media_type in ["image", "video", "document"]:
                payload[media_type]["caption"] = caption
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                
                if response.status_code in (200, 201):
                    result = response.json()
                    message_id = result.get("messages", [{}])[0].get("id")
                    logger.info(f"WhatsApp {media_type} sent to {to_phone}: {message_id}")
                    return {
                        "success": True,
                        "message_id": message_id,
                        "status": "sent",
                    }
                else:
                    error_msg = f"WhatsApp API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
                    
        except Exception as e:
            logger.error(f"Failed to send WhatsApp {media_type} to {to_phone}: {e}")
            return {"success": False, "error": str(e)}
    
    async def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify WhatsApp webhook (for Meta webhook verification).
        
        Args:
            mode: Verification mode
            token: Verification token
            challenge: Challenge string
            
        Returns:
            Challenge string if verified, None otherwise
        """
        verify_token = _settings.WHATSAPP_VERIFY_TOKEN
        
        if mode == "subscribe" and token == verify_token:
            logger.info("WhatsApp webhook verified")
            return challenge
        
        logger.warning("WhatsApp webhook verification failed")
        return None
    
    async def parse_incoming_message(self, data: Dict) -> Optional[Dict[str, Any]]:
        """Parse incoming WhatsApp webhook message.
        
        Args:
            data: Webhook payload from Meta
            
        Returns:
            Parsed message or None
        """
        try:
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            
            # Check if it's a message
            if "messages" not in value:
                return None
            
            message = value["messages"][0]
            
            # Extract phone numbers
            from_phone = message.get("from")
            to_phone = value.get("metadata", {}).get("display_phone_number")
            
            # Extract message content
            msg_type = message.get("type")
            content = ""
            media_url = None
            
            if msg_type == "text":
                content = message.get("text", {}).get("body", "")
            elif msg_type == "image":
                media_url = message.get("image", {}).get("id")
                content = message.get("image", {}).get("caption", "")
            elif msg_type == "document":
                media_url = message.get("document", {}).get("id")
                content = message.get("document", {}).get("filename", "")
            elif msg_type == "audio":
                media_url = message.get("audio", {}).get("id")
            
            # Extract message ID
            message_id = message.get("id")
            
            # Extract timestamp
            timestamp = int(message.get("timestamp", 0))
            
            return {
                "message_id": message_id,
                "from_phone": from_phone,
                "to_phone": to_phone,
                "channel": "whatsapp",
                "direction": "inbound",
                "content": content,
                "media_url": media_url,
                "message_type": msg_type,
                "timestamp": timestamp,
                "raw": message,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse WhatsApp message: {e}")
            return None