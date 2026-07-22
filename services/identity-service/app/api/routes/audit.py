"""Read-only ADMIN audit-log endpoint."""
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.common.responses import success_response
from app.db.dependencies import get_db
from app.models.user import User, UserRole
from app.repositories.audit_repository import AuditRepository
from app.schemas.audit import AuditLogItem, AuditLogPage
from app.security.dependencies import require_roles
from app.services.audit_service import sanitize_audit_details


router = APIRouter(tags=["audit"])


@router.get("/audit-logs")
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    result: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    if date_from is not None and date_to is not None and date_from > date_to:
        raise AppException(
            "VALIDATION_ERROR",
            "date_from must not be later than date_to",
            status_code=422,
        )

    items, total = AuditRepository(db).list_filtered(
        page=page,
        page_size=page_size,
        action=action,
        actor_user_id=actor_user_id,
        result=result,
        date_from=date_from,
        date_to=date_to,
    )
    response = AuditLogPage(
        items=[
            AuditLogItem(
                id=item.id,
                actor_user_id=item.actor_user_id,
                action=item.action,
                ip_address=item.ip_address,
                result=item.result,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                details=sanitize_audit_details(item.details),
                created_at=item.created_at,
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
    return success_response(data=response.model_dump(mode="json"))
