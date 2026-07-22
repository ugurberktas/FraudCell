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

    def get_by_id(self, user_id) -> User | None:
        return self.session.get(User, user_id)

    def get_active_customer_by_gsm(self, gsm: str) -> User | None:
        statement = select(User).where(
            User.gsm == gsm,
            User.role == UserRole.CUSTOMER,
            User.is_active.is_(True),
        )
        return self.session.scalar(statement)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email).limit(1))

    def get_by_email_for_update(self, email: str) -> User | None:
        statement = (
            select(User)
            .where(User.email == email)
            .limit(1)
            .with_for_update()
        )
        return self.session.scalar(statement)

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
