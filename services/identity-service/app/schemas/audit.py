"""Read-only audit log response schemas."""
from datetime import datetime
import uuid

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    ip_address: str | None
    result: str
    resource_type: str | None
    resource_id: str | None
    details: dict | list | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogItem]
    page: int
    page_size: int
    total: int
