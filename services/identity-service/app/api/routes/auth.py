"""Authentication, token, current-user, and Admin staff routes."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.responses import success_response
from app.core.config import settings
from app.db.dependencies import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthUserResponse,
    CustomerLoginOtpRequest,
    CustomerLoginRequest,
    RefreshTokenRequest,
    StaffLoginRequest,
)
from app.schemas.staff import StaffCreate
from app.security.client_ip import get_client_ip
from app.security.dependencies import get_current_user, require_roles
from app.models.user import UserRole
from app.services.auth_service import AuthService
from app.services.staff_service import StaffService
from app.services.token_service import TokenService


router = APIRouter(tags=["authentication"])


@router.post("/customers/login/otp/request")
def request_customer_login_otp(
    payload: CustomerLoginOtpRequest, db: Session = Depends(get_db)
):
    AuthService(db).request_customer_login_otp(payload.gsm)
    return success_response(
        data={
            "message": (
                "If an active customer account exists, an OTP will be delivered. "
                "The OTP is not shown in this response."
            )
        }
    )


@router.post("/customers/login")
def customer_login(
    payload: CustomerLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    response = AuthService(db).customer_login(
        payload.gsm, payload.otp_code, get_client_ip(request)
    )
    return success_response(data=response.model_dump(mode="json"))


@router.post("/staff/login")
def staff_login(
    payload: StaffLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    response = AuthService(db).staff_login(
        str(payload.email), payload.password, get_client_ip(request)
    )
    return success_response(data=response.model_dump(mode="json"))


@router.post("/tokens/refresh")
def refresh_tokens(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    issued, user = TokenService(db).rotate(
        payload.refresh_token, get_client_ip(request)
    )
    response = AuthService._token_response(user, issued)
    return success_response(data=response.model_dump(mode="json"))


@router.post("/tokens/logout")
def logout(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    TokenService(db).logout(payload.refresh_token, get_client_ip(request))
    return success_response(data={"message": "Session logged out"})


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    response = AuthUserResponse(
        id=current_user.id,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        email=current_user.email,
        gsm=current_user.gsm,
        role=current_user.role.value,
    )
    return success_response(data=response.model_dump(mode="json"))


@router.post("/staff/accounts", status_code=201)
def create_staff_account(
    payload: StaffCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    response = StaffService(db).create_staff(
        payload,
        actor_user_id=admin.id,
        ip_address=get_client_ip(request),
    )
    return success_response(data=response.model_dump(mode="json"), status_code=201)
