from __future__ import annotations


class WritingService:
    @staticmethod
    def maybe_handle(prompt: str) -> str | None:
        text = prompt.strip().lower()
        if "leave letter" in text or ("leave" in text and "letter" in text):
            return (
                "Subject: Leave Request\n\n"
                "Dear Sir/Madam,\n\n"
                "I am writing to request leave for [number of days] from [start date] to [end date] due to [reason]. "
                "I will make sure my pending work is completed or handed over before my leave begins.\n\n"
                "Kindly approve my leave request.\n\n"
                "Thank you.\n\n"
                "Yours sincerely,\n"
                "[Your Name]"
            )
        if text.startswith("write ") and "email" in text:
            return (
                "Subject: [Subject]\n\n"
                "Dear [Recipient],\n\n"
                "I hope you are doing well. I am writing to [state the purpose clearly]. "
                "Please let me know if you need any additional details.\n\n"
                "Thank you.\n\n"
                "Best regards,\n"
                "[Your Name]"
            )
        return None
