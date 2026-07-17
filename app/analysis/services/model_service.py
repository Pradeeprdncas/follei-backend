import os
import asyncio
import logging
import functools
import re
from typing import Any, Dict, List, Optional

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TextIteratorStreamer,
)
from peft import PeftModel

from app.config.settings import get_settings
from app.analysis.services.tool_service import ToolService
from app.analysis.pipelines.language_service import LanguageService

_settings = get_settings()

logger = logging.getLogger(__name__)


async def _get_history(session_id: str, limit: int = None) -> List[Dict[str, str]]:
    try:
        from app.analysis.services.memory_service import memory_service
        return memory_service.get_history(session_id, limit)
    except Exception:
        return []


class ModelService:
    model = None
    tokenizer = None

    @staticmethod
    def _clean_incomplete_tail(text: str) -> str:
        text = text.strip()
        if not text or text[-1] in ".!?:)]":
            return text
        match = list(re.finditer(r"[.!?](?:\s|$)", text))
        if match:
            end = match[-1].end()
            cleaned = text[:end].strip()
            if len(cleaned) >= max(40, len(text) * 0.55):
                return cleaned
        return text

    @classmethod
    def _should_use_history(cls, prompt: str) -> bool:
        text = prompt.strip().lower()
        follow_up_starters = (
            "explain",
            "why",
            "how",
            "tell me more",
            "more",
            "continue",
            "give example",
            "example",
            "what about",
            "and",
            "then",
        )
        fresh_question_starters = (
            "what is ",
            "what are ",
            "who is ",
            "where is ",
            "define ",
            "meaning of ",
            "tell me about ",
        )
        if text.startswith(fresh_question_starters):
            return False
        return text.startswith(follow_up_starters)

    @classmethod
    async def initialize(cls):
        cls.tokenizer = AutoTokenizer.from_pretrained(
            _settings.MODEL_BASE,
            trust_remote_code=True,
            truncation_side="left",
        )
        base_model = AutoModelForCausalLM.from_pretrained(
            _settings.MODEL_BASE,
            trust_remote_code=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        lora_config = os.path.join(_settings.LORA_OUTPUT_DIR, "adapter_config.json") if _settings.LORA_OUTPUT_DIR else None
        if lora_config and os.path.exists(lora_config):
            cls.model = PeftModel.from_pretrained(
                base_model,
                _settings.LORA_OUTPUT_DIR,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )
            logger.info("Model loaded with LoRA adapters from %s", _settings.LORA_OUTPUT_DIR)
        else:
            cls.model = base_model
            logger.info("Base model loaded perfectly without LoRA corruption.")
        cls.model.eval()

    @classmethod
    def _build_prompt(cls, prompt: str, history: List[Dict[str, str]], retrieved_docs: List[str], tools: Optional[List[Dict[str, Any]]] = None) -> str:
        context = "\n".join([f"User: {m['content']}" if m['role'] == 'user' else f"Assistant: {m['content']}" for m in history])
        docs = "\n\n".join([f"Document {idx + 1}: {doc}" for idx, doc in enumerate(retrieved_docs)])
        tool_section = "\nTools available:\n" + "\n".join([f"{t['name']}: {t.get('description', '')}" for t in tools]) if tools else ""
        language_instruction = LanguageService.response_instruction(LanguageService.detect(prompt))
        return f"System: You are a helpful AI assistant. {language_instruction} Give accurate, natural, professional answers. Use conversation context only when it helps.\n{tool_section}\nContext:\n{context}\nRetrieved Knowledge:\n{docs}\nUser: {prompt}\nAssistant:"

    @classmethod
    def _build_model_prompt(cls, prompt: str, history: List[Dict[str, str]], retrieved_docs: List[str], tools: Optional[List[Dict[str, Any]]] = None) -> str:
        if cls.tokenizer is not None and getattr(cls.tokenizer, "chat_template", None):
            docs = "\n\n".join(retrieved_docs)
            tool_names = ", ".join([t["name"] for t in tools]) if tools else ""
            system_parts = [
                "You are a helpful real-time AI chatbot.",
                LanguageService.response_instruction(LanguageService.detect(prompt)),
                "Answer the latest user question directly, accurately, and professionally.",
                "Give a complete answer; do not stop mid-sentence.",
                "Keep answers concise: usually 2 short paragraphs or up to 4 bullets.",
                "Avoid long introductions and unnecessary examples.",
                "If speech-to-text has small wording errors, infer the intended Tamil or English question before answering.",
                "Do not talk about detected sentiment or emotion unless the user asks about it.",
                "When the user asks you to write, draft, summarize, translate, or create something, complete the task directly.",
                "Do not use childish analogies such as toy box, big box, little helper, buttons and lights, unless the user asks for a kids explanation.",
                "Use previous chat messages only for follow-up questions.",
                "Do not continue an old answer when the user asks a new question.",
                "For 'what is' questions, give a clear definition and 2 to 3 key points.",
            ]
            if docs:
                system_parts.append(f"Use this retrieved knowledge when relevant:\n{docs}")
            if tool_names:
                system_parts.append(f"Available tools: {tool_names}")
            messages = [
                {"role": "system", "content": "\n\n".join(system_parts)},
            ]
            for message in history:
                role = message.get("role", "user") if isinstance(message, dict) else message.role
                content = message.get("content", "") if isinstance(message, dict) else message.content
                messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": prompt})
            return cls.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        prompt_text = cls._build_prompt(prompt, history, retrieved_docs, tools)
        return prompt_text

    @classmethod
    async def generate_response(cls, session_id: str, prompt: str, history: List[Dict[str, str]], retrieved_docs: List[str], tools: Optional[List[Dict[str, Any]]] = None) -> str:
        if cls.tokenizer is None or cls.model is None:
            logger.warning("Model not initialized. Returning echo response.")
            return f"[Model not loaded] Echo: {prompt}"

        try:
            conversation = await _get_history(session_id, _settings.MAX_HISTORY)

            normalized_history = []
            for msg in conversation + history:
                role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "role", "user")
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                msg_dict = {"role": role, "content": content}
                if msg_dict not in normalized_history:
                    normalized_history.append(msg_dict)

            if normalized_history and normalized_history[-1]["role"] == "user" and normalized_history[-1]["content"] == prompt:
                normalized_history.pop()

            if cls._should_use_history(prompt):
                normalized_history = normalized_history[-6:]
            else:
                normalized_history = []

            prompt_text = cls._build_model_prompt(prompt, normalized_history, retrieved_docs, tools)
            inputs = cls.tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=_settings.MAX_TOKENS)
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            with torch.inference_mode():
                output = cls.model.generate(
                    **inputs,
                    max_new_tokens=_settings.MAX_NEW_TOKENS,
                    temperature=_settings.TEMPERATURE,
                    top_p=_settings.TOP_P,
                    repetition_penalty=1.05,
                    pad_token_id=cls.tokenizer.pad_token_id if cls.tokenizer.pad_token_id is not None else cls.tokenizer.eos_token_id,
                )
            new_tokens = output[0][inputs["input_ids"].shape[-1]:]
            text = cls.tokenizer.decode(new_tokens, skip_special_tokens=True)
            return cls._clean_incomplete_tail(text)
        except Exception as e:
            logger.exception("Generation failed")
            raise

    @classmethod
    async def stream_response(cls, session_id: str, prompt: str, history: List[Dict[str, str]], retrieved_docs: List[str], tools: Optional[List[Dict[str, Any]]] = None):
        conversation = await _get_history(session_id, _settings.MAX_HISTORY)

        normalized_history = []
        for msg in conversation + history:
            role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "role", "user")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            msg_dict = {"role": role, "content": content}
            if msg_dict not in normalized_history:
                normalized_history.append(msg_dict)

        if normalized_history and normalized_history[-1]["role"] == "user" and normalized_history[-1]["content"] == prompt:
            normalized_history.pop()

        if cls._should_use_history(prompt):
            normalized_history = normalized_history[-6:]
        else:
            normalized_history = []

        prompt_text = cls._build_model_prompt(prompt, normalized_history, retrieved_docs, tools)
        inputs = cls.tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=_settings.MAX_TOKENS)
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        streamer = TextIteratorStreamer(cls.tokenizer, timeout=10.0, skip_prompt=True)
        generate_kwargs = dict(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_new_tokens=_settings.MAX_NEW_TOKENS,
            temperature=_settings.TEMPERATURE,
            top_p=_settings.TOP_P,
            repetition_penalty=1.05,
            pad_token_id=cls.tokenizer.pad_token_id if cls.tokenizer.pad_token_id is not None else cls.tokenizer.eos_token_id,
            streamer=streamer,
        )

        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, functools.partial(cls.model.generate, **generate_kwargs))

        async for token in cls._stream_tokens(streamer):
            yield token

        await task

    @classmethod
    async def _stream_tokens(cls, streamer):
        while True:
            token = await asyncio.to_thread(lambda: next(streamer, None))
            if token is None:
                break
            yield token.encode("utf-8")


model_service = ModelService()
