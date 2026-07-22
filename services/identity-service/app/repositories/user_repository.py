"""User persistence operations."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def contact_exists(self, gsm: str, email: str | None) -> bool:
        conditions = [User.gsm == gsm]
        if email is not None:
            conditions.append(User.email == email)
        statement = select(User.id).where(or_(*conditions)).limit(1)
        return self.session.scalar(statement) is not None

    def create_customer(
        self,
        *,
        first_name: str,
        last_name: str,
        gsm: str,
        email: str | None,
    ) -> User:
        user = User(
            first_name=first_name,
            last_name=last_name,
            gsm=gsm,
            email=email,
            password_hash=None,
            role=UserRole.CUSTOMER,
        )
        self.session.add(user)
        self.session.flush()
        return user
