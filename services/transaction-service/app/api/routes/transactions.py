"""Transaction creation and read endpoints."""
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.clients.ai_client import AIClient, get_ai_client
from app.common.responses import success_response
from app.db.dependencies import get_db
from app.schemas.transaction import TransactionCreate
from app.security.dependencies import get_current_user, require_roles
from app.security.tokens import AuthenticatedUser, UserRole
from app.services.transaction_service import TransactionService


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", status_code=201)
def create_transaction(
    payload: TransactionCreate,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles(UserRole.CUSTOMER)),
    db: Session = Depends(get_db),
    ai_client: AIClient = Depends(get_ai_client),
):
    data = TransactionService(db, ai_client).create(
        payload,
        customer_id=user.user_id,
        request_id=request.state.request_id,
    )
    return success_response(data=data, status_code=201)


@router.get("/me")
def list_my_transactions(
    user: AuthenticatedUser = Depends(require_roles(UserRole.CUSTOMER)),
    db: Session = Depends(get_db),
):
    return success_response(
        data={"items": TransactionService(db, get_ai_client()).list_for_customer(user.user_id)}
    )


@router.get("/{transaction_id}")
def get_transaction(
    transaction_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(
        data=TransactionService(db, get_ai_client()).get_for_user(transaction_id, user)
    )
