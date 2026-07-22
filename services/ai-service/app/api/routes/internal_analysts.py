"""Internal-only analyst profile synchronization."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.responses import success_response
from app.db.dependencies import get_db
from app.schemas.scoring import AnalystSyncRequest
from app.security.internal import require_internal_service_key
from app.services.analyst_service import AnalystService


router = APIRouter(prefix="/internal/analysts", tags=["internal-analysts"])


@router.post("/sync")
def sync_analyst(
    payload: AnalystSyncRequest,
    _: None = Depends(require_internal_service_key),
    db: Session = Depends(get_db),
):
    return success_response(data=AnalystService(db).sync(payload))
