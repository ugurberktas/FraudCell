import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.common.responses import success_response
from app.db.session import get_db
from app.security.dependencies import get_current_user, require_roles
from app.security.tokens import AuthenticatedUser, UserRole
from app.services.profile_service import ProfileService

router = APIRouter(tags=["gamification"])


@router.get("/leaderboard")
def leaderboard(
    period: str = Query(default="daily", pattern="^(daily|weekly)$"),
    limit: int = Query(default=10, ge=1, le=10),
    _: AuthenticatedUser = Depends(require_roles(UserRole.ANALYST, UserRole.SUPERVISOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return success_response({"period": period, "items": ProfileService(db).leaderboard(period, limit)})


@router.get("/profiles/me")
def my_profile(
    user: AuthenticatedUser = Depends(require_roles(UserRole.ANALYST)),
    db: Session = Depends(get_db),
):
    return success_response(ProfileService(db).profile(user.user_id))


@router.get("/profiles/{analyst_id}")
def analyst_profile(
    analyst_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role is UserRole.CUSTOMER:
        raise AppException("FORBIDDEN", "Access is forbidden", 403)
    if user.role is UserRole.ANALYST and user.user_id != analyst_id:
        raise AppException("FORBIDDEN", "Access is forbidden", 403)
    return success_response(ProfileService(db).profile(analyst_id))
