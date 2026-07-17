from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SendResult:
    success: bool
    provider_message_id: str | None = None
    status: str = ""
    raw_response: dict | None = None
    error: str | None = None


class MessagingProvider(ABC):
    @abstractmethod
    async def send(self, recipient: str, body: str, subject: str | None = None,
                   html_body: str | None = None, sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...
