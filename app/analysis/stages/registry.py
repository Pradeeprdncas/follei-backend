"""Stage registry — pluggable pipeline stage management.

Stages are registered by name and executed in registration order.
Configuration can enable/disable, reorder, or add new stages
at runtime without changing pipeline code.
"""
from app.analysis.stages.base import AnalysisStage, PipelineContext
from loguru import logger


class StageRegistry:
    """Registry of named AnalysisStage implementations."""

    def __init__(self):
        self._stages: dict[str, AnalysisStage] = {}
        self._order: list[str] = []

    def register(self, stage: AnalysisStage) -> None:
        """Register a stage. Replaces any existing stage with the same name."""
        self._stages[stage.name] = stage
        if stage.name not in self._order:
            self._order.append(stage.name)
        logger.debug(f"Stage registered: {stage.name}")

    def unregister(self, name: str) -> None:
        """Remove a stage by name."""
        self._stages.pop(name, None)
        if name in self._order:
            self._order.remove(name)

    def get(self, name: str) -> AnalysisStage | None:
        return self._stages.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._order)

    def set_order(self, names: list[str]) -> None:
        """Override execution order. Unknown names are skipped."""
        self._order = [n for n in names if n in self._stages]

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Run all registered stages in order.

        If any stage fails, subsequent stages are skipped and the
        error is recorded on the context.
        """
        for name in self._order:
            stage = self._stages[name]
            if not stage.enabled:
                logger.info(f"Stage skipped (disabled): {name}")
                continue
            try:
                ctx = stage.execute(ctx)
                logger.debug(f"Stage completed: {name}")
            except Exception as e:
                logger.error(f"Stage failed: {name} — {e}")
                ctx.error = f"{name}: {e}"
                break
        return ctx
