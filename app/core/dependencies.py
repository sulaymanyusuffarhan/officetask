import secrets

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.roles import ADMIN, EDITOR, HEAD, PLANNER, SHIFT_LEADER, STAFF
from app.db.session import get_db
from app.models.models import User


ALL_ROLES = {HEAD, PLANNER, EDITOR, SHIFT_LEADER, STAFF, ADMIN}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    user = db.get(User, user_id)
    if user is None or not user.active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role_id not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission")
        return user
    return dependency


def require_csrf(request: Request) -> None:
    # Login also requires an anonymous-session token issued by /api/auth/csrf.
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = request.session.get("csrf_token")
    provided = request.headers.get("x-csrf-token")
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


BUSINESS_MANAGERS = (HEAD, EDITOR)
TASK_VIEW_ROLES = (HEAD, EDITOR, SHIFT_LEADER, STAFF)
PLANNING_ROLES = (HEAD, PLANNER)
ADMIN_ROLE = (ADMIN,)
