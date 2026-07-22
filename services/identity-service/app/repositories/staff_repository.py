"""Staff user and profile persistence operations."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.staff_profile import StaffProfile
from app.models.user import User, UserRole


class StaffRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email).limit(1))

    def create_staff(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        role: UserRole,
        password_hash: str,
        specializations: list[str],
        regions: list[str],
        max_active_cases: int,
    ) -> User:
        user = User(
            first_name=first_name,
            last_name=last_name,
            gsm=None,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        user.staff_profile = StaffProfile(
            specializations=specializations,
            regions=regions,
            max_active_cases=max_active_cases,
        )
        self.session.add(user)
        self.session.flush()
        return user
