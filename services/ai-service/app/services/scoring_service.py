"""Model inference plus analyst assignment transaction."""
from sqlalchemy.orm import Session

from app.ml.engine import RiskEngine
from app.schemas.scoring import AssignmentStatus, ScoreRequest
from app.services.assignment_service import AssignmentResult, AssignmentService


class ScoringService:
    def __init__(self, session: Session, engine: RiskEngine) -> None:
        self.session = session
        self.engine = engine

    def score_and_assign(self, payload: ScoreRequest) -> dict:
        prediction = self.engine.predict(payload.model_dump())
        try:
            assignment = (
                AssignmentService(self.session).assign(prediction.fraud_type)
                if prediction.decision != "ONAY"
                else AssignmentResult(None, AssignmentStatus.QUEUED, None)
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return {
            "risk_score": prediction.risk_score,
            "fraud_type": prediction.fraud_type,
            "decision": prediction.decision,
            "risk_level": prediction.risk_level,
            "risk_reasons": prediction.risk_reasons,
            "model_version": prediction.model_version,
            "assigned_analyst_id": (
                str(assignment.assigned_analyst_id)
                if assignment.assigned_analyst_id
                else None
            ),
            "assignment_status": assignment.assignment_status.value,
            "assignment_score": assignment.assignment_score,
        }
