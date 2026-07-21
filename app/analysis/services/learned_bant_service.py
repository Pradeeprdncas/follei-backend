from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import joblib
import numpy as np

from app.config.settings import get_settings

_settings = get_settings()


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

        return result

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
