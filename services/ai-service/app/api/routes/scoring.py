"""Authenticated model scoring endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.responses import success_response
from app.db.dependencies import get_db
from app.ml.dependencies import get_risk_engine
from app.ml.engine import RiskEngine
from app.schemas.scoring import ScoreRequest
from app.security.internal import require_internal_service_key
from app.services.scoring_service import ScoringService


router = APIRouter(tags=["scoring"])


@router.post("/score-and-assign")
def score_and_assign(
    payload: ScoreRequest,
    _: None = Depends(require_internal_service_key),
    db: Session = Depends(get_db),
    engine: RiskEngine = Depends(get_risk_engine),
):
    return success_response(data=ScoringService(db, engine).score_and_assign(payload))
