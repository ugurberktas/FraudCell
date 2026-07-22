"""Staff account creation and Admin bootstrap orchestration."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.models.user import User, UserRole
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import StaffCreate, StaffResponse, StaffRole
from app.security.passwords import hash_password, validate_password_policy
from app.services.audit_service import AuditAction, AuditResult, AuditService


_DUPLICATE_MESSAGE = "A staff account with the provided email already exists"


@dataclass(frozen=True)
class BootstrapAdminResult:
    email: str
    created: bool


class StaffService:
    def __init__(
        self, session: Session, repository: StaffRepository | None = None
    ) -> None:
        self.session = session
        self.repository = repository or StaffRepository(session)

    def create_staff(
        self,
        request: StaffCreate,
        *,
        actor_user_id=None,
        ip_address: str | None = None,
    ) -> StaffResponse:
        try:
            if self.repository.get_by_email(str(request.email)) is not None:
                raise AppException(
                    "STAFF_ALREADY_EXISTS", _DUPLICATE_MESSAGE, status_code=409
                )
            return self._create_and_commit(
                request,
                actor_user_id=actor_user_id,
                ip_address=ip_address,
            )
        except AppException:
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise AppException(
                "STAFF_ALREADY_EXISTS", _DUPLICATE_MESSAGE, status_code=409
            ) from exc
        except Exception:
            self.session.rollback()
            raise

    def bootstrap_admin(self, request: StaffCreate) -> BootstrapAdminResult:
        if request.role != StaffRole.ADMIN:
            raise ValueError("Admin bootstrap requires the ADMIN role")

        try:
            existing = self.repository.get_by_email(str(request.email))
            if existing is not None:
                self.session.rollback()
                if existing.role == UserRole.ADMIN:
                    return BootstrapAdminResult(email=str(request.email), created=False)
                raise AppException(
                    "BOOTSTRAP_ADMIN_ROLE_CONFLICT",
                    "The bootstrap email belongs to a different account role",
                    status_code=409,
                )

            self._create_and_commit(request)
            return BootstrapAdminResult(email=str(request.email), created=True)
        except AppException:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            existing = self.repository.get_by_email(str(request.email))
            if existing is not None and existing.role == UserRole.ADMIN:
                self.session.rollback()
                return BootstrapAdminResult(email=str(request.email), created=False)
            self.session.rollback()
            raise AppException(
                "BOOTSTRAP_ADMIN_ROLE_CONFLICT",
                "The bootstrap email belongs to a different account role",
                status_code=409,
            )
        except Exception:
            self.session.rollback()
            raise

    def _create_and_commit(
        self,
        request: StaffCreate,
        *,
        actor_user_id=None,
        ip_address: str | None = None,
    ) -> StaffResponse:
        validate_password_policy(request.password)
        password_hash = hash_password(request.password)
        user = self.repository.create_staff(
            first_name=request.first_name,
            last_name=request.last_name,
            email=str(request.email),
            role=UserRole(request.role.value),
            password_hash=password_hash,
            specializations=request.specializations,
            regions=request.regions,
            max_active_cases=request.max_active_cases,
        )
        if actor_user_id is not None:
            AuditService(self.session).record(
                actor_user_id=actor_user_id,
                action=AuditAction.STAFF_ACCOUNT_CREATED,
                result=AuditResult.SUCCESS,
                ip_address=ip_address,
                resource_type="USER",
                resource_id=str(user.id),
                details={"created_role": user.role.value},
            )
        self.session.commit()
        self.session.refresh(user)
        return self._to_response(user)

    @staticmethod
    def _to_response(user: User) -> StaffResponse:
        profile = user.staff_profile
        return StaffResponse(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            role=user.role,
            specializations=profile.specializations,
            regions=profile.regions,
            max_active_cases=profile.max_active_cases,
        )
