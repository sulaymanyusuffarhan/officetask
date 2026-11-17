import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import AuditLog, User


def record_audit(db: Session, actor: User | None, action: str, entity_type: str, entity_id: object, details: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
    ))
