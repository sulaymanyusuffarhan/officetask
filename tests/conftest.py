from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.core.roles import ADMIN, EDITOR, HEAD, PLANNER, SHIFT_LEADER, STAFF, ROLE_NAMES
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.models import Department, Role, Shift, User


@pytest.fixture
def system(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'office-test.db'}",
                           connect_args={"check_same_thread": False, "timeout": 15})
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_db
    import app.api.routes as api_routes
    api_routes._login_failures.clear()
    with TestingSession() as db:
        for role_id, name in ROLE_NAMES.items():
            db.add(Role(id=role_id, name=name))
        dept = Department(name="News")
        morning = Shift(name="Morning", start_time="08:00", end_time="16:00")
        evening = Shift(name="Evening", start_time="16:00", end_time="23:00")
        db.add_all([dept, morning, evening]); db.flush()
        users = {}
        for username, role in [("head", HEAD), ("planner", PLANNER), ("editor", EDITOR),
                               ("employee", STAFF), ("employee2", STAFF), ("leader", SHIFT_LEADER), ("admin", ADMIN)]: 
            user = User(username=username, full_name=username.title(), password_hash=hash_password("test-password-1234"),
                        role_id=role, department_id=dept.id)
            db.add(user); db.flush(); users[username] = user.id
        db.commit()
        context = {**users, "department": dept.id, "morning": morning.id, "evening": evening.id}
    client = TestClient(app)
    try:
        yield client, context
    finally:
        client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def login(client, username):
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    response = client.post("/api/auth/login", data={"username": username, "password": "test-password-1234"},
                           headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def mutate(client, token, method, url, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    headers["X-CSRF-Token"] = token
    return getattr(client, method)(url, headers=headers, **kwargs)


def publish_editor_shift(client, users):
    planner_token = login(client, "planner")
    work_date = date.today()
    week_start = work_date - timedelta(days=work_date.weekday())
    plan = mutate(client, planner_token, "post", "/api/timetables", json={"week_start": week_start.isoformat()}).json()
    allocated = mutate(client, planner_token, "post", f"/api/timetables/{plan['id']}/assignments", json={
        "work_date": work_date.isoformat(), "shift_id": 1, "employee_id": users["employee"],
        "editor_id": users["editor"], "department_id": 1, "responsibility": "Reporting"})
    assert allocated.status_code == 201, allocated.text
    submitted = mutate(client, planner_token, "post", f"/api/timetables/{plan['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    client.post("/api/auth/logout", headers={"X-CSRF-Token": planner_token})
    head_token = login(client, "head")
    approved = mutate(client, head_token, "post", f"/api/timetables/{plan['id']}/review", data={"decision": "approve", "comment": "Approved"})
    assert approved.status_code == 200, approved.text
    published = mutate(client, head_token, "post", f"/api/timetables/{plan['id']}/publish")
    assert published.status_code == 200, published.text
    client.post("/api/auth/logout", headers={"X-CSRF-Token": head_token})
    return login(client, "editor")
