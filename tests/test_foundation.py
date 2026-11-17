from conftest import login, mutate, publish_editor_shift


def test_authentication_csrf_and_role_enforcement(system):
    client, users = system
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert client.post("/api/auth/login", data={"username": "head", "password": "test-password-1234"}).status_code == 403
    head_token = login(client, "head")
    assert client.get("/api/reports/dashboard").status_code == 200
    assert client.get("/api/audit").status_code == 200
    # Authenticated state changes are rejected without the signed-session CSRF token.
    assert client.post("/api/timetables", json={"week_start": "2026-11-16"}).status_code == 403
    client.post("/api/auth/logout", headers={"X-CSRF-Token": head_token})
    login(client, "employee")
    assert client.get("/api/reports/dashboard").status_code == 403
    assert client.get("/api/tasks").status_code == 200
    assert users["head"] != users["employee"]


def test_weekly_timetable_approval_and_published_version_immutability(system):
    client, users = system
    planner_token = login(client, "planner")
    created = mutate(client, planner_token, "post", "/api/timetables", json={"week_start": "2026-11-16"})
    assert created.status_code == 201, created.text
    timetable_id = created.json()["id"]
    assignment = mutate(client, planner_token, "post", f"/api/timetables/{timetable_id}/assignments", json={
        "work_date": "2026-11-16", "shift_id": 1, "employee_id": users["employee"],
        "leader_id": users["leader"], "editor_id": users["editor"], "department_id": 1,
        "responsibility": "Reporting"})
    assert assignment.status_code == 201
    changed = mutate(client, planner_token, "put", f"/api/timetables/{timetable_id}/assignments/{assignment.json()['id']}", json={
        "work_date": "2026-11-16", "shift_id": 1, "employee_id": users["employee"], "leader_id": users["leader"],
        "editor_id": users["editor"], "department_id": 1, "responsibility": "Jambo / Asubuhi hii",
        "reason": "Editorial roster adjustment"})
    assert changed.status_code == 200
    # The same employee cannot be booked into overlapping shift hours on that date.
    conflict = mutate(client, planner_token, "post", f"/api/timetables/{timetable_id}/assignments", json={
        "work_date": "2026-11-16", "shift_id": 1, "employee_id": users["employee"],
        "responsibility": "Second assignment"})
    assert conflict.status_code == 409
    assert mutate(client, planner_token, "post", f"/api/timetables/{timetable_id}/submit").status_code == 200
    client.post("/api/auth/logout", headers={"X-CSRF-Token": planner_token})
    head_token = login(client, "head")
    review = mutate(client, head_token, "post", f"/api/timetables/{timetable_id}/review",
                    data={"decision": "approve", "comment": "Reviewed"})
    assert review.status_code == 200 and review.json()["status"] == "Approved"
    assert mutate(client, head_token, "post", f"/api/timetables/{timetable_id}/publish").status_code == 200
    locked = mutate(client, head_token, "post", f"/api/timetables/{timetable_id}/assignments", json={
        "work_date": "2026-11-17", "shift_id": 2, "employee_id": users["employee"]})
    assert locked.status_code == 409
    version = mutate(client, head_token, "post", f"/api/timetables/{timetable_id}/new-version", data={"reason": "Updated staff allocation"})
    assert version.status_code == 201
    assert version.json()["version"] == 2
    client.post("/api/auth/logout", headers={"X-CSRF-Token": head_token})
    login(client, "employee")
    published = client.get("/api/timetables?week_start=2026-11-16")
    assert published.status_code == 200
    assert len(published.json()) == 1
    assert published.json()[0]["status"] == "Published"


def test_employee_submission_independent_verification_and_reports(system):
    client, users = system
    editor_token = publish_editor_shift(client, users)
    task_response = mutate(client, editor_token, "post", "/api/tasks", json={
        "title": "Prepare daily bulletin", "description": "Prepare a report", "instructions": "Submit notes",
        "employee_ids": [users["employee"]], "department_id": 1, "shift_id": 1,
        "assignment_date": "2026-11-17", "start_date": "2026-11-17",
        "deadline": "2026-11-17T18:00:00", "priority": "High"})
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()[0]["id"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": editor_token})
    staff_token = login(client, "employee")
    assert mutate(client, staff_token, "post", f"/api/tasks/{task_id}/acknowledge").status_code == 200
    assert mutate(client, staff_token, "post", f"/api/tasks/{task_id}/start").status_code == 200
    submitted = mutate(client, staff_token, "post", f"/api/tasks/{task_id}/submit", data={"report": "Completed the bulletin"})
    assert submitted.status_code == 200 and submitted.json()["status"] == "Submitted"
    client.post("/api/auth/logout", headers={"X-CSRF-Token": staff_token})
    editor_token = login(client, "editor")
    submission = client.get(f"/api/tasks/{task_id}/submissions").json()[0]
    verification = mutate(client, editor_token, "post", f"/api/submissions/{submission['id']}/verify",
                          json={"decision": "approve", "comment": "Checked and complete"})
    assert verification.status_code == 200 and verification.json()["status"] == "Verified"
    client.post("/api/auth/logout", headers={"X-CSRF-Token": editor_token})
    head_token = login(client, "head")
    performance = client.get("/api/reports/performance?start=2026-11-17&end=2026-11-17")
    assert performance.status_code == 200
    row = next(r for r in performance.json()["employees"] if r["employee_id"] == users["employee"])
    assert row["assigned"] == row["submitted"] == row["verified"] == 1
    assert row["submission_rate"] == row["verified_completion_rate"] == 100.0
    analytics = client.get("/api/reports/analytics?start=2026-11-17&end=2026-11-17")
    assert analytics.status_code == 200 and analytics.json()["by_day"][0]["label"] == "2026-11-17"
    assert client.get("/api/reports/tasks.xlsx?start=2026-11-17&end=2026-11-17").status_code == 200
    assert client.get("/api/reports/tasks.pdf?start=2026-11-17&end=2026-11-17").status_code == 200
    assert client.get("/api/audit").json()


def test_employee_cannot_verify_their_own_submission(system):
    client, users = system
    head_token = login(client, "head")
    task = mutate(client, head_token, "post", "/api/tasks", json={"title": "Own task", "employee_ids": [users["head"]],
        "assignment_date": "2026-11-17", "start_date": "2026-11-17", "deadline": "2026-11-17T23:00:00",
        "priority": "Normal"})
    assert task.status_code == 201
    task_id = task.json()[0]["id"]
    submitted = mutate(client, head_token, "post", f"/api/tasks/{task_id}/submit", data={"report": "My work"})
    assert submitted.status_code == 200
    result = mutate(client, head_token, "post", f"/api/submissions/{submitted.json()['submission_id']}/verify",
                    json={"decision": "approve", "comment": "self"})
    assert result.status_code == 403


def test_private_attachment_validation_and_authorized_download(system, monkeypatch, tmp_path):
    import app.api.routes as routes
    monkeypatch.setattr(routes.settings, "upload_dir", str(tmp_path))
    client, users = system
    head_token = login(client, "head")
    created = mutate(client, head_token, "post", "/api/tasks", json={"title": "Capture event", "employee_ids": [users["employee"]],
        "assignment_date": "2026-11-17", "start_date": "2026-11-17", "deadline": "2026-11-17T23:00:00", "priority": "Normal"})
    task_id = created.json()[0]["id"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": head_token})
    staff_token = login(client, "employee")
    bad = mutate(client, staff_token, "post", f"/api/tasks/{task_id}/submit", data={"report": "Work attached"},
                 files={"files": ("bad.exe", b"MZ\x00", "application/octet-stream")})
    assert bad.status_code == 422
    good = mutate(client, staff_token, "post", f"/api/tasks/{task_id}/submit", data={"report": "Work attached"},
                  files={"files": ("evidence.png", b"\x89PNG\r\n\x1a\nnot-executable", "image/png")})
    assert good.status_code == 200
    files = client.get(f"/api/tasks/{task_id}/submissions").json()[0]["attachments"]
    assert files[0]["name"] == "evidence.png"
    download = client.get(f"/api/attachments/{files[0]['id']}")
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG")
    assert len(list(tmp_path.iterdir())) == 1


def test_admin_can_manage_accounts_but_does_not_gain_business_permissions(system):
    client, _ = system
    token = login(client, "admin")
    created = mutate(client, token, "post", "/api/users", json={"username": "newstaff", "full_name": "New Staff",
        "password": "an-initial-password-987", "role_id": "staff"})
    assert created.status_code == 201, created.text
    assert client.get("/api/tasks").status_code == 403
    assert client.get("/api/timetables").status_code == 403
    assert client.get("/api/audit").status_code == 200


def test_login_rate_limit(system):
    client, _ = system
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    for _ in range(5):
        response = client.post("/api/auth/login", data={"username": "missing", "password": "not-a-valid-password"},
                               headers={"X-CSRF-Token": csrf})
        assert response.status_code == 401
    limited = client.post("/api/auth/login", data={"username": "missing", "password": "not-a-valid-password"},
                          headers={"X-CSRF-Token": csrf})
    assert limited.status_code == 429


def test_correction_resubmission_and_head_reopen_audit(system):
    client, users = system
    editor_token = publish_editor_shift(client, users)
    task_response = mutate(client, editor_token, "post", "/api/tasks", json={"title": "Update local bulletin", "employee_ids": [users["employee"]],
        "assignment_date": "2026-11-17", "start_date": "2026-11-17", "deadline": "2026-11-17T23:00:00", "priority": "Normal"})
    task_id = task_response.json()[0]["id"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": editor_token})
    employee_token = login(client, "employee")
    first = mutate(client, employee_token, "post", f"/api/tasks/{task_id}/submit", data={"report": "First attempt"})
    client.post("/api/auth/logout", headers={"X-CSRF-Token": employee_token})
    editor_token = login(client, "editor")
    first_submission = client.get(f"/api/tasks/{task_id}/submissions").json()[0]
    correction = mutate(client, editor_token, "post", f"/api/submissions/{first_submission['id']}/verify",
        json={"decision": "request_correction", "comment": "Add the missing source citation"})
    assert correction.status_code == 200 and correction.json()["status"] == "Correction Requested"
    client.post("/api/auth/logout", headers={"X-CSRF-Token": editor_token})
    employee_token = login(client, "employee")
    resubmitted = mutate(client, employee_token, "post", f"/api/tasks/{task_id}/submit", data={"report": "Revised with source citation"})
    assert resubmitted.status_code == 200 and resubmitted.json()["status"] == "Resubmitted"
    client.post("/api/auth/logout", headers={"X-CSRF-Token": employee_token})
    editor_token = login(client, "editor")
    submissions = client.get(f"/api/tasks/{task_id}/submissions").json()
    verified = mutate(client, editor_token, "post", f"/api/submissions/{submissions[-1]['id']}/verify",
        json={"decision": "approve", "comment": "Citation verified"})
    assert verified.status_code == 200 and verified.json()["status"] == "Verified"
    client.post("/api/auth/logout", headers={"X-CSRF-Token": editor_token})
    head_token = login(client, "head")
    reopened = mutate(client, head_token, "post", f"/api/tasks/{task_id}/reopen", data={"reason": "Management requested updated attribution"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "Correction Requested"
    audit = client.get("/api/audit?limit=500").json()
    assert any(x["action"] == "verified_task_reopened" and "Management requested" in x["details"]["reason"] for x in audit)


def test_local_branding_and_security_headers(system):
    client, _ = system
    page = client.get("/")
    assert page.status_code == 200
    assert "/static/images/emblem.png" in page.text
    assert "/static/images/tbc-digital-logo.jpg" in page.text
    assert page.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/images/emblem.png").headers["content-type"] == "image/png"
    assert client.get("/static/images/tbc-digital-logo.jpg").headers["content-type"] == "image/jpeg"
    assert client.get("/api/health/live").json() == {"status": "alive"}


def test_editor_people_and_task_assignment_are_scoped_to_published_shift(system):
    client, users = system
    editor_token = publish_editor_shift(client, users)
    people = client.get("/api/people")
    assert people.status_code == 200
    assert [x["id"] for x in people.json()] == [users["employee"]]
    denied = mutate(client, editor_token, "post", "/api/tasks", json={"title": "Out of shift task",
        "employee_ids": [users["employee2"]], "assignment_date": "2026-11-17", "start_date": "2026-11-17",
        "deadline": "2026-11-17T23:00:00", "priority": "Normal"})
    assert denied.status_code == 403
