from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

import joblib
import numpy as np

from app.config.settings import get_settings

_settings = get_settings()

# Keyword-triggered sentence extraction, not an LLM call: there is no working
# local LLM configured (see model_manager.py's missing GGUF file), so this is
# a deterministic stand-in for "extract this lead's stated requirements from
# their speech/text" that costs nothing and never hallucinates a need that
# wasn't actually said.
_REQUIREMENT_KEYWORDS = re.compile(
    r"\b(need|needs|needed|require|requires|required|requirement|want|wants|wanted|"
    r"looking for|budget|deadline|timeline|must have|has to|have to|expect|expects|"
    r"prefer|would like|asking for)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _extract_requirement_phrases(text: str, max_len: int = 220) -> list[str]:
    """Pull out the sentences of *text* that state a need/want/constraint."""
    phrases: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if sentence and _REQUIREMENT_KEYWORDS.search(sentence):
            phrases.append(sentence[:max_len])
    return phrases


class LearnedBANTService:
    """Inference for a supervised BANT regressor trained on labeled conversations.

    When the trained model file does not exist, falls back to LLM-based
    qualification scoring (BANT + MEDDIC) via LLMQualificationService.
    """

    artifact: dict[str, Any] | None = None

    @classmethod
    async def predict(
        cls,
        text: str,
        conversation_id: str | None = None,
        tenant_id: str | None = None,
        lead_id: str | None = None,
    ) -> dict[str, Any] | None:
        path = Path(_settings.BANT_MODEL_PATH)
        if cls.artifact is None:
            if path.is_file():
                loaded = joblib.load(path)
                if not isinstance(loaded, dict) or not {"vectorizer", "model", "labels"} <= loaded.keys():
                    raise ValueError(f"Invalid learned BANT artifact: {path}")
                cls.artifact = loaded
        if cls.artifact is not None:
            matrix = cls.artifact["vectorizer"].transform([text])
            values = np.asarray(cls.artifact["model"].predict(matrix)[0], dtype=float)
            values = np.clip(values, 0.0, 1.0)
            return {name: round(float(value), 4) for name, value in zip(cls.artifact["labels"], values)}

        # ── No trained model — use LLM qualification scoring ──
        return await cls._llm_qualify(text, conversation_id, tenant_id, lead_id)

    @classmethod
    def predict_sync(cls, text: str) -> dict[str, float] | None:
        """Sync wrapper for backward compatibility.

        When no trained model file exists, returns None so the caller
        (lead_intelligence_service) falls through to its heuristic fallback.
        """
        path = Path(_settings.BANT_MODEL_PATH)
        if cls.artifact is None:
            if not path.is_file():
                return None
            loaded = joblib.load(path)
            if not isinstance(loaded, dict) or not {"vectorizer", "model", "labels"} <= loaded.keys():
                raise ValueError(f"Invalid learned BANT artifact: {path}")
            cls.artifact = loaded
        matrix = cls.artifact["vectorizer"].transform([text])
        values = np.asarray(cls.artifact["model"].predict(matrix)[0], dtype=float)
        values = np.clip(values, 0.0, 1.0)
        return {name: round(float(value), 4) for name, value in zip(cls.artifact["labels"], values)}

    @classmethod
    async def _llm_qualify(
        cls,
        text: str,
        conversation_id: str | None,
        tenant_id: str | None,
        lead_id: str | None,
    ) -> dict[str, Any]:
        from app.analysis.services.llm_qualification_service import LLMQualificationService

        bant = await LLMQualificationService.analyze(
            transcript=text, framework_name="BANT", conversation_id=conversation_id
        )
        meddic = await LLMQualificationService.analyze(
            transcript=text, framework_name="MEDDIC", conversation_id=conversation_id
        )

        bant_scores = {k: v.get("score") for k, v in bant.get("scores", {}).items()}
        meddic_scores = {k: v.get("score") for k, v in meddic.get("scores", {}).items()}

        result: dict[str, Any] = {
            "bant": bant_scores,
            "meddic": meddic_scores,
            "bant_overall": bant.get("overall_score"),
            "meddic_overall": meddic.get("overall_score"),
            "source": (
                "evidence_heuristic"
                if bant.get("source") == "evidence_heuristic" or meddic.get("source") == "evidence_heuristic"
                else "llm"
            ),
        }

        # Persist only for real persisted conversations; demo IDs such as "demo" are not UUIDs.
        try:
            has_persistable_conversation = bool(conversation_id and tenant_id and UUID(str(conversation_id)))
        except (ValueError, TypeError):
            has_persistable_conversation = False
        if has_persistable_conversation:
            await cls._persist_qualification(
                transcript=text,
                framework_name="BANT",
                result=bant,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                lead_id=lead_id,
            )
            await cls._persist_qualification(
                transcript=text,
                framework_name="MEDDIC",
                result=meddic,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                lead_id=lead_id,
            )

        # Carry qualification evidence forward across turns/sessions for this lead
        # (FerretDB tenant_context), independent of whether the Postgres-side
        # persistence above ran. Only needs tenant_id + lead_id, not a
        # persistable conversation_id.
        cls._accumulate_ferret_memory(tenant_id, lead_id, text, bant_scores, meddic_scores, result["source"])

        return result

    @classmethod
    def _accumulate_ferret_memory(
        cls,
        tenant_id: str | None,
        lead_id: str | None,
        text: str,
        bant_scores: dict[str, Any],
        meddic_scores: dict[str, Any],
        source: str,
    ) -> None:
        """Merge this turn's BANT/MEDDIC evidence into the lead's FerretDB memory.

        Scores are evidence-presence signals, so once a component is
        established (e.g. budget confirmed in turn 1) a later, unrelated turn
        should not silently erase it — hence merge-by-max rather than overwrite.
        build_agent_context()'s customer_context already reads this same
        tenant_context document, so anything written here is automatically
        available to chat_pipeline()/workers on the very next turn.
        """
        if not tenant_id or not lead_id:
            return
        try:
            from datetime import datetime, timezone
            from app.services.knowledge.context_store import get_context, upsert_context

            existing = get_context(tenant_id=tenant_id, subject_type="lead", subject_id=lead_id) or {}
            prior_bant = existing.get("bant") or {}
            prior_meddic = existing.get("meddic") or {}
            merged_bant = {
                key: max(float(prior_bant.get(key) or 0), float(value or 0))
                for key, value in bant_scores.items()
            }
            merged_meddic = {
                key: max(float(prior_meddic.get(key) or 0), float(value or 0))
                for key, value in meddic_scores.items()
            }
            history = list(existing.get("qualification_history") or [])
            history.append({
                "text": text[:300],
                "bant": bant_scores,
                "meddic": meddic_scores,
                "source": source,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            history = history[-20:]

            requirements = list(existing.get("requirements") or [])
            for phrase in _extract_requirement_phrases(text):
                if phrase not in {item["text"] for item in requirements}:
                    requirements.append({"text": phrase, "at": datetime.now(timezone.utc).isoformat()})
            requirements = requirements[-30:]

            upsert_context(
                tenant_id=tenant_id,
                subject_type="lead",
                subject_id=lead_id,
                updates={
                    "bant": merged_bant,
                    "meddic": merged_meddic,
                    "qualification_history": history,
                    "requirements": requirements,
                },
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to accumulate lead qualification memory: %s", exc)

    @classmethod
    async def _persist_qualification(
        cls,
        transcript: str,
        framework_name: str,
        result: dict[str, Any],
        conversation_id: str,
        tenant_id: str,
        lead_id: str | None,
    ) -> None:
        """Write a qualification result to lead_qualifications and qualification_answers."""
        from sqlalchemy import text as sa_text
        from app.config.database import SessionLocal

        try:
            with SessionLocal() as session:
                resolved_lead_id = lead_id
                if not resolved_lead_id:
                    # Try to find a lead for this conversation
                    row = session.execute(
                        sa_text("SELECT lead_id FROM conversations WHERE id = :cid"),
                        {"cid": conversation_id},
                    ).fetchone()
                    if row:
                        resolved_lead_id = str(row[0])

                if not resolved_lead_id:
                    # Cannot persist without a lead
                    return

                # Get the framework_id
                fw_row = session.execute(
                    sa_text(
                        "SELECT id FROM qualification_frameworks "
                        "WHERE tenant_id = :tid AND name = :name AND is_active = true"
                    ),
                    {"tid": tenant_id, "name": framework_name},
                ).fetchone()
                if not fw_row:
                    return
                framework_id = fw_row[0]

                # Build reasoning string from all component evidence
                components = result.get("scores", {})
                evidence_parts = []
                for comp_key, comp_val in components.items():
                    ev = comp_val.get("evidence", "") if isinstance(comp_val, dict) else ""
                    if ev:
                        evidence_parts.append(f"{comp_key}: {ev}")
                reasoning = "; ".join(evidence_parts) if evidence_parts else None

                # Insert lead_qualification
                qual_row = session.execute(
                    sa_text(
                        "INSERT INTO lead_qualifications "
                        "(tenant_id, lead_id, framework_id, score, status, reasoning) "
                        "VALUES (:tid, :lid, :fwid, :score, :status, :reasoning) "
                        "RETURNING id"
                    ),
                    {
                        "tid": tenant_id,
                        "lid": resolved_lead_id,
                        "fwid": framework_id,
                        "score": result.get("overall_score"),
                        "status": result.get("status", "completed"),
                        "reasoning": reasoning,
                    },
                ).fetchone()
                qualification_id = qual_row[0]

                # Insert one qualification_answer per component
                for comp_key, comp_val in components.items():
                    if not isinstance(comp_val, dict):
                        continue
                    score = comp_val.get("score")
                    evidence = comp_val.get("evidence", "")
                    session.execute(
                        sa_text(
                            "INSERT INTO qualification_answers "
                            "(tenant_id, qualification_id, question, answer, score, evidence) "
                            "VALUES (:tid, :qid, :question, :answer, :score, :evidence)"
                        ),
                        {
                            "tid": tenant_id,
                            "qid": qualification_id,
                            "question": comp_key,
                            "answer": evidence or "",
                            "score": score,
                            "evidence": evidence or "",
                        },
                    )

                session.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to persist %s qualification: %s", framework_name, exc
            )
