"""Customer registration transaction orchestration."""
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.customer import CustomerRegisterRequest
from app.services.otp_service import OtpService


_DUPLICATE_MESSAGE = "A customer with the provided contact information already exists"


class CustomerService:
    def __init__(
        self,
        session: Session,
        user_repository: UserRepository | None = None,
        otp_service: OtpService | None = None,
    ) -> None:
        self.session = session
        self.users = user_repository or UserRepository(session)
        self.otp = otp_service or OtpService(session)

    def register(self, request: CustomerRegisterRequest) -> User:
        try:
            if self.users.contact_exists(request.gsm, request.email):
                raise AppException("CUSTOMER_ALREADY_EXISTS", _DUPLICATE_MESSAGE, status_code=409)

            now = datetime.now(timezone.utc)
            challenge = self.otp.verify(request.gsm, request.otp_code, now)
            user = self.users.create_customer(
                first_name=request.first_name,
                last_name=request.last_name,
                gsm=request.gsm,
                email=request.email,
            )
            challenge.consumed_at = now
            self.session.commit()
            self.session.refresh(user)
            return user
        except AppException:
            # Invalid OTP attempts are committed by OtpService so their counter
            # persists. Other domain failures leave no pending writes.
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise AppException(
                "CUSTOMER_ALREADY_EXISTS", _DUPLICATE_MESSAGE, status_code=409
            ) from exc
        except Exception:
            self.session.rollback()
            raise
