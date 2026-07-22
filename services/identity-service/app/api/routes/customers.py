"""Customer GSM/OTP endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.responses import success_response
from app.db.dependencies import get_db
from app.schemas.customer import CustomerRegisterRequest, CustomerResponse, OtpRequest
from app.services.customer_service import CustomerService
from app.services.otp_service import OtpService


router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/otp/request")
def request_customer_otp(payload: OtpRequest, db: Session = Depends(get_db)):
    challenge = OtpService(db).request_challenge(payload.gsm)
    return success_response(
        data={
            "challenge_id": str(challenge.id),
            "expires_at": challenge.expires_at.isoformat(),
            "message": (
                "Demo mode: in a real system the OTP would be delivered by SMS "
                "and would not be shown in this response."
            ),
        },
    )


@router.post("/register", status_code=201)
def register_customer(
    payload: CustomerRegisterRequest, db: Session = Depends(get_db)
):
    user = CustomerService(db).register(payload)
    response = CustomerResponse.model_validate(user).model_dump(mode="json")
    return success_response(data=response, status_code=201)
