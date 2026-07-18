"""Repository for a tenant's selected onboarding goals (max 3, enforced by the router)."""
import uuid

from sqlalchemy.orm import Session

from app.models.onboarding_goal import OnboardingGoal


class OnboardingGoalRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_tenant(self, tenant_id) -> list[str]:
        rows = self.db.query(OnboardingGoal).filter(OnboardingGoal.tenant_id == tenant_id).all()
        return [row.goal for row in rows]

    def replace_for_tenant(self, tenant_id, goals: list[str]) -> list[str]:
        self.db.query(OnboardingGoal).filter(OnboardingGoal.tenant_id == tenant_id).delete()
        seen: list[str] = []
        for goal in goals:
            if goal in seen:
                continue
            seen.append(goal)
            self.db.add(OnboardingGoal(id=uuid.uuid4(), tenant_id=tenant_id, goal=goal))
        self.db.commit()
        return seen
