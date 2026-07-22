"""Risk case list and state transition endpoints."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.responses import success_response
from app.db.dependencies import get_db
from app.models import CaseStatus
from app.schemas.transaction import (
    CaseAssignRequest,
    CaseDecisionRequest,
    CustomerResponseRequest,
)
from app.security.dependencies import require_roles
from app.security.tokens import AuthenticatedUser, UserRole
from app.services.case_service import CaseService


router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("/assigned-to-me")
def assigned_to_me(
    user: AuthenticatedUser = Depends(require_roles(UserRole.ANALYST)),
    db: Session = Depends(get_db),
):
    return success_response(data={"items": CaseService(db).list_assigned(user.user_id)})


@router.get("")
def list_cases(
    status: CaseStatus | None = Query(default=None),
    user: AuthenticatedUser = Depends(
        require_roles(UserRole.SUPERVISOR, UserRole.ADMIN)
    ),
    db: Session = Depends(get_db),
):
    return success_response(data={"items": CaseService(db).list_all(status)})


@router.post("/{case_id}/assign")
def assign_case(
    case_id: uuid.UUID,
    payload: CaseAssignRequest,
    user: AuthenticatedUser = Depends(require_roles(UserRole.SUPERVISOR)),
    db: Session = Depends(get_db),
):
    return success_response(
        data=CaseService(db).assign(case_id, payload.analyst_id, user.user_id)
    )


@router.post("/{case_id}/start")
def start_case(
    case_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_roles(UserRole.ANALYST)),
    db: Session = Depends(get_db),
):
    return success_response(data=CaseService(db).start(case_id, user.user_id))


@router.post("/{case_id}/request-verification")
def request_verification(
    case_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_roles(UserRole.ANALYST)),
    db: Session = Depends(get_db),
):
    return success_response(
        data=CaseService(db).request_verification(case_id, user.user_id)
    )


@router.post("/{case_id}/customer-response")
def customer_response(
    case_id: uuid.UUID,
    payload: CustomerResponseRequest,
    user: AuthenticatedUser = Depends(require_roles(UserRole.CUSTOMER)),
    db: Session = Depends(get_db),
):
    return success_response(
        data=CaseService(db).customer_response(case_id, user.user_id, payload.response)
    )


@router.post("/{case_id}/decision")
def decide_case(
    case_id: uuid.UUID,
    payload: CaseDecisionRequest,
    user: AuthenticatedUser = Depends(require_roles(UserRole.ANALYST)),
    db: Session = Depends(get_db),
):
    return success_response(
        data=CaseService(db).decide(
            case_id, user.user_id, payload.decision, payload.note
        )
    )
