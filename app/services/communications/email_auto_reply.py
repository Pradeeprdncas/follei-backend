"""Email Reply Generator — isolated swap point for finetuned model.

Usage:
    generator = EmailReplyGenerator()
    result = await generator.generate_reply(
        message="What is your pricing?",
        tenant_id="...",
        lead_id="...",
        conversation_id="...",
        conversation_history=[...],
    )

To swap with a finetuned model, subclass or replace this class:
    class FinetunedEmailReplyGenerator(EmailReplyGenerator):
        async def generate_reply(self, ...) -> dict: ...
"""
from typing import Any
from loguru import logger
from app.config.settings import get_settings


class EmailReplyGenerator:
    """Generates email replies using the RAG pipeline.

    This class is the designated swap point for a finetuned model.
    Replace `generate_reply` to use a dedicated email-completion model
    while keeping the same signature and return contract.
    """

    def __init__(self):
        self._settings = get_settings()
        self._confidence_threshold = self._settings.BREVO_AUTO_REPLY_CONFIDENCE_THRESHOLD

    async def generate_reply(
        self,
        message: str,
        tenant_id: str,
        lead_id: str,
        conversation_id: str,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Generate an email reply for an inbound message.

        Args:
            message: The inbound email body text.
            tenant_id: Tenant UUID.
            lead_id: Lead UUID.
            conversation_id: Conversation UUID.
            conversation_history: Previous messages in this conversation
                (role, content) for context.

        Returns:
            dict with keys:
                - success (bool)
                - answer (str | None): generated reply text
                - confidence (float): 0.0–1.0
                - intent (str | None): detected intent label
                - error (str | None): if success is False
        """
        try:
            from app.services.ai.router import get_ai_router

            router = get_ai_router()

            context = {
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "conversation_id": conversation_id,
                "channel": "email",
                "conversation_history": conversation_history or [],
            }

            result = await router.process_request(
                query=message,
                context=context,
                user_intent={"source": "email_auto_reply"},
            )

            if not result.get("success"):
                logger.warning(f"AI router returned failure: {result.get('error')}")
                return {
                    "success": False,
                    "answer": None,
                    "confidence": 0.0,
                    "intent": None,
                    "error": result.get("error", "AI router returned no success"),
                }

            answer = result.get("answer")
            confidence = result.get("confidence", 0.0)
            intent = result.get("intent")

            if not answer:
                return {
                    "success": False,
                    "answer": None,
                    "confidence": 0.0,
                    "intent": None,
                    "error": "Empty answer from AI router",
                }

            if confidence < self._confidence_threshold:
                logger.info(f"Confidence {confidence:.2f} below threshold {self._confidence_threshold}, marking low")
                return {
                    "success": True,
                    "answer": answer,
                    "confidence": confidence,
                    "intent": intent,
                    "below_threshold": True,
                }

            return {
                "success": True,
                "answer": answer,
                "confidence": confidence,
                "intent": intent,
                "below_threshold": False,
            }

        except Exception as e:
            logger.error(f"Email reply generation failed: {e}")
            return {
                "success": False,
                "answer": None,
                "confidence": 0.0,
                "intent": None,
                "error": str(e),
            }

    async def calculate_confidence(self, answer: str, message: str) -> float:
        """Score the generated reply for relevance.

        Override this when using a finetuned model that provides
        its own confidence scoring.

        Args:
            answer: Generated reply text.
            message: Original inbound message.

        Returns:
            Float 0.0–1.0 representing confidence.
        """
        if not answer or not message:
            return 0.0
        overlap = len(set(answer.lower().split()) & set(message.lower().split()))
        total = len(set(message.lower().split()))
        if total == 0:
            return 0.0
        return min(overlap / total, 1.0)
