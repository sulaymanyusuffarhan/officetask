import csv
import io
from datetime import date

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.api.social import METRICS
from app.main import app
from conftest import login, mutate


PLATFORMS = ("youtube", "facebook", "instagram", "x", "tiktok")


def client_for():
    return TestClient(app)


def configure_social(client, users, officer="editor"):
    token = login(client, "head")
    for platform in PLATFORMS:
        response = mutate(client, token, "post", "/api/social/accounts", json={
            "platform": platform, "account_name": f"Test Office {platform.title()}",
            "account_handle": f"@test-office-{platform}", "profile_url": f"https://example.org/{platform}"})
        assert response.status_code == 201, response.text
    designated = mutate(client, token, "put", "/api/social/officers", json={"user_ids": [users[officer]]})
    assert designated.status_code == 200
    return token


def metrics(**changes):
    values = {key: None for key in METRICS}
    values.update(changes)
    return values


def weekly_body(platform="youtube", reporting_week="2026-01-05", reporting_date="2026-01-09", account_id=None, **changes):
    body = {"platform": platform, "reporting_date": reporting_date, "reporting_week": reporting_week,
            "metrics": metrics(**changes), "best_content": "Test-only sample content",
            "recommendations": "Test-only review recommendation"}
    if account_id is not None:
        body["account_id"] = account_id
    return body


def evidence(client, token, report_id, filename="analytics.png", data=b"\x89PNG\r\n\x1a\nunit-test-fixture"):
    return mutate(client, token, "post", f"/api/social/weekly/{report_id}/evidence",
                  files={"files": (filename, data, "image/png" if filename.endswith(".png") else "application/pdf")})


def test_manual_accounts_metrics_evidence_permissions_and_approval(system, monkeypatch, tmp_path):
    import app.api.social as social_routes
    monkeypatch.setattr(social_routes.settings, "upload_dir", str(tmp_path))
    client, users = system
    configure_social(client, users)
    page=client.get("/")
    assert page.status_code==200 and 'data-view="social"' in page.text and 'id="view-social"' in page.text
    assert 'rel="icon"' in page.text and client.get("/static/images/emblem.png").status_code==200
    assert client.get("/static/js/social-charts.js").status_code==200
    listed = client.get("/api/social/accounts")
    assert listed.status_code == 200 and len(listed.json()) == 5
    assert {x["platform"] for x in listed.json()} == set(PLATFORMS)

    staff = client_for()
    staff_token = login(staff, "employee")
    assert staff.get("/api/social/weekly").status_code == 403
    youtube_id = next(a["id"] for a in listed.json() if a["platform"] == "youtube")
    assert mutate(staff, staff_token, "put", f"/api/social/accounts/{youtube_id}", json={
        "account_name": "Forbidden", "account_handle": "@forbidden"}).status_code == 403
    for username in ("planner", "leader", "admin"):
        denied_client=client_for();login(denied_client,username)
        assert denied_client.get("/api/social/weekly").status_code==403
        denied_client.close()

    editor = client_for()
    editor_token = login(editor, "editor")
    assert editor.get("/api/social/access").json()["allowed"] is True
    missing_metrics = weekly_body()
    del missing_metrics["metrics"]["impressions"]
    assert mutate(editor, editor_token, "post", "/api/social/weekly", json=missing_metrics).status_code == 422
    invalid_week = weekly_body(reporting_week="2026-01-06")
    assert mutate(editor, editor_token, "post", "/api/social/weekly", json=invalid_week).status_code == 422

    first = mutate(editor, editor_token, "post", "/api/social/weekly", json=weekly_body(
        audience_start=1000, audience_end=1100, new_followers=120, lost_followers=20, reach=2000,
        impressions=5000, views=3000, likes=80, comments=10, shares=10, saves=None,
        posts_published=4, videos_published=2))
    assert first.status_code == 201, first.text
    report_id = first.json()["id"]
    calc = first.json()["calculations"]
    assert calc["net_follower_growth"] == 100
    assert calc["audience_growth_percent"] == 10.0
    assert calc["engagement_rate_percent"] == 3.33
    assert calc["engagement_denominator"] == "views"
    assert first.json()["metrics"]["saves"] is None
    assert first.json()["source_kind"] == "manual"
    assert mutate(editor, editor_token, "post", f"/api/social/weekly/{report_id}/submit").status_code == 409
    from openpyxl import Workbook
    xlsx_io=io.BytesIO(); Workbook().save(xlsx_io)
    evidence_files=[
        ("files",("platform-screenshot.png",b"\x89PNG\r\n\x1a\nimage-fixture","image/png")),
        ("files",("platform-report.pdf",b"%PDF-1.4\nfixture","application/pdf")),
        ("files",("platform-export.xlsx",xlsx_io.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ("files",("platform-export.csv",b"metric,value\nreach,2000\n","text/csv")),
    ]
    with_evidence=mutate(editor,editor_token,"post",f"/api/social/weekly/{report_id}/evidence",files=evidence_files)
    assert with_evidence.status_code==201 and len(with_evidence.json()["evidence"])==4
    for item,signature in zip(with_evidence.json()["evidence"],[b"\x89PNG",b"%PDF-",b"PK",b"metric,value"]):
        download=editor.get(f"/api/social/evidence/{item['id']}")
        assert download.status_code==200 and download.content.startswith(signature)
    assert mutate(editor, editor_token, "post", f"/api/social/weekly/{report_id}/submit").status_code == 200
    duplicate = mutate(editor, editor_token, "post", "/api/social/weekly", json=weekly_body(audience_start=1))
    assert duplicate.status_code == 409

    head = client_for()
    head_token = login(head, "head")
    assert mutate(head,head_token,"post",f"/api/social/weekly/{report_id}/review",
                   json={"decision":"correction","comment":""}).status_code==422
    approved = mutate(head, head_token, "post", f"/api/social/weekly/{report_id}/review",
                      json={"decision": "approve", "comment": "Verified against the submitted evidence"})
    assert approved.status_code == 200 and approved.json()["status"] == "Approved"
    assert approved.json()["reviewed_by_id"] == users["head"]
    assert mutate(editor, editor_token, "put", f"/api/social/weekly/{report_id}", json=weekly_body(
        audience_start=1000, audience_end=1200)).status_code == 409

    # A separate report exercises correction and resubmission rather than only direct approval.
    second = mutate(editor, editor_token, "post", "/api/social/weekly", json=weekly_body(
        reporting_week="2026-01-12", reporting_date="2026-01-16", audience_start=1100, audience_end=1150,
        new_followers=70, lost_followers=20, reach=2200, impressions=5300, views=3300, likes=90,
        comments=12, shares=8, saves=5, posts_published=3, videos_published=1))
    assert second.status_code == 201
    assert evidence(editor, editor_token, second.json()["id"]).status_code == 201
    assert mutate(editor, editor_token, "post", f"/api/social/weekly/{second.json()['id']}/submit").status_code == 200
    returned = mutate(head, head_token, "post", f"/api/social/weekly/{second.json()['id']}/review",
                      json={"decision": "correction", "comment": "Please confirm the end-of-week count"})
    assert returned.status_code == 200 and returned.json()["status"] == "Returned for Correction"
    corrected = weekly_body(reporting_week="2026-01-12", reporting_date="2026-01-16", audience_start=1100,
        audience_end=1170, new_followers=70, lost_followers=0, reach=2200, impressions=5300, views=3300,
        likes=90, comments=12, shares=8, saves=5, posts_published=3, videos_published=1)
    resubmitted = mutate(editor, editor_token, "put", f"/api/social/weekly/{second.json()['id']}", json=corrected)
    assert resubmitted.status_code == 200 and resubmitted.json()["status"] == "Draft"
    assert mutate(editor, editor_token, "post", f"/api/social/weekly/{second.json()['id']}/submit").status_code == 200
    assert mutate(head, head_token, "post", f"/api/social/weekly/{second.json()['id']}/review",
                  json={"decision": "approve", "comment": "Correction checked"}).json()["status"] == "Approved"
    rejected_report=mutate(editor,editor_token,"post","/api/social/weekly",json=weekly_body("facebook",audience_start=500,audience_end=510,reach=1000,likes=10,comments=2,shares=1))
    assert rejected_report.status_code==201
    assert evidence(editor,editor_token,rejected_report.json()["id"]).status_code==201
    mutate(editor,editor_token,"post",f"/api/social/weekly/{rejected_report.json()['id']}/submit")
    rejected=mutate(head,head_token,"post",f"/api/social/weekly/{rejected_report.json()['id']}/review",
                    json={"decision":"reject","comment":"The attached screenshot does not show the selected week"})
    assert rejected.status_code==200 and rejected.json()["status"]=="Rejected"
    corrected_rejected=mutate(editor,editor_token,"put",f"/api/social/weekly/{rejected_report.json()['id']}",
                              json=weekly_body("facebook",audience_start=500,audience_end=511,reach=1000,likes=11,comments=2,shares=1))
    assert corrected_rejected.status_code==200 and corrected_rejected.json()["status"]=="Draft"
    staff.close(); editor.close(); head.close()


def test_multiple_accounts_are_reported_and_consolidated_separately(system, monkeypatch, tmp_path):
    import app.api.social as social_routes
    monkeypatch.setattr(social_routes.settings, "upload_dir", str(tmp_path))
    client, users = system
    head_token = configure_social(client, users)
    original = next(a for a in client.get("/api/social/accounts").json() if a["platform"] == "youtube")
    duplicate = mutate(client, head_token, "post", "/api/social/accounts", json={
        "platform": "youtube", "account_name": "Second YouTube channel", "account_handle": "@test-office-youtube"})
    assert duplicate.status_code == 409
    created = mutate(client, head_token, "post", "/api/social/accounts", json={
        "platform": "youtube", "account_name": "Second YouTube channel", "account_handle": "@test-office-youtube-2"})
    assert created.status_code == 201, created.text
    second_id = created.json()["id"]
    accounts = client.get("/api/social/accounts").json()
    assert len(accounts) == 6 and {a["id"] for a in accounts if a["platform"] == "youtube"} == {original["id"], second_id}

    editor = client_for(); editor_token = login(editor, "editor")
    import_row = {"platform": "youtube", "account_handle": "@test-office-youtube-2",
                  "reporting_date": "2026-02-06", "reporting_week": "2026-02-02",
                  **{key: "N/A" for key in METRICS}, "best_content": "", "recommendations": ""}
    import_fields = ["platform", "account_handle", "reporting_date", "reporting_week", *METRICS,
                     "best_content", "recommendations"]
    csv_buffer = io.StringIO(); writer = csv.DictWriter(csv_buffer, fieldnames=import_fields)
    writer.writeheader(); writer.writerow(import_row); import_data = csv_buffer.getvalue().encode()
    preview = mutate(editor, editor_token, "post", "/api/social/imports/preview",
                     files={"file": ("multi-account.csv", import_data, "text/csv")})
    assert preview.status_code == 200 and preview.json()["ready_count"] == 1
    assert preview.json()["rows"][0]["account_id"] == second_id
    import_row["account_handle"] = ""
    csv_buffer = io.StringIO(); writer = csv.DictWriter(csv_buffer, fieldnames=import_fields)
    writer.writeheader(); writer.writerow(import_row)
    ambiguous_import = mutate(editor, editor_token, "post", "/api/social/imports/preview",
                              files={"file": ("ambiguous.csv", csv_buffer.getvalue().encode(), "text/csv")})
    assert ambiguous_import.status_code == 200 and ambiguous_import.json()["error_count"] == 1
    ambiguous = mutate(editor, editor_token, "post", "/api/social/weekly", json=weekly_body())
    assert ambiguous.status_code == 422 and "specific" in ambiguous.text
    first = mutate(editor, editor_token, "post", "/api/social/weekly", json=weekly_body(
        account_id=original["id"], audience_start=100, audience_end=110, new_followers=10,
        lost_followers=0, reach=200, views=300, likes=10, comments=2, shares=1))
    second = mutate(editor, editor_token, "post", "/api/social/weekly", json=weekly_body(
        account_id=second_id, audience_start=1000, audience_end=1025, new_followers=25,
        lost_followers=0, reach=500, views=700, likes=20, comments=4, shares=2))
    assert first.status_code == 201 and second.status_code == 201
    assert evidence(editor, editor_token, first.json()["id"]).status_code == 201
    assert evidence(editor, editor_token, second.json()["id"]).status_code == 201
    for report in (first.json(), second.json()):
        assert mutate(editor, editor_token, "post", f"/api/social/weekly/{report['id']}/submit").status_code == 200
        assert mutate(client, head_token, "post", f"/api/social/weekly/{report['id']}/review",
                      json={"decision": "approve", "comment": "Verified per account evidence"}).status_code == 200
    quarter = mutate(editor, editor_token, "post", "/api/social/quarters/generate", json={"year": 2026, "quarter": 1})
    assert quarter.status_code == 201, quarter.text
    youtube_rows = [p for p in quarter.json()["snapshot"]["platforms"] if p["platform"] == "youtube"]
    assert {p["account_id"] for p in youtube_rows} == {original["id"], second_id}
    assert {p["audience_start"] for p in youtube_rows} == {100, 1000}
    editor.close(); client.close()


def test_import_preview_templates_commit_source_and_duplicate_validation(system, monkeypatch, tmp_path):
    import app.api.social as social_routes
    monkeypatch.setattr(social_routes.settings, "upload_dir", str(tmp_path))
    client, users = system
    configure_social(client, users)
    token = login(client, "editor")
    template = client.get("/api/social/template.csv")
    assert template.status_code == 200 and "audience_start" in template.text
    xlsx_template = client.get("/api/social/template.xlsx")
    assert xlsx_template.status_code == 200 and xlsx_template.content.startswith(b"PK")
    workbook = load_workbook(io.BytesIO(xlsx_template.content), read_only=True)
    assert "reporting_week" in list(workbook.active.values)[0]
    workbook.close()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["platform", "reporting_date", "reporting_week", *METRICS,
                                                "best_content", "recommendations"])
    writer.writeheader()
    row = {"platform": "facebook", "reporting_date": "2026-01-09", "reporting_week": "2026-01-05",
           **{k: "N/A" for k in METRICS}, "audience_start": "200", "audience_end": "210", "new_followers": "12",
           "lost_followers": "2", "reach": "500", "impressions": "900", "views": "N/A", "likes": "30",
           "comments": "5", "shares": "2", "saves": "N/A", "posts_published": "2", "videos_published": "0",
           "best_content": "Imported test fixture", "recommendations": "Imported fixture recommendation"}
    writer.writerow(row)
    filedata = output.getvalue().encode()
    preview = mutate(client, token, "post", "/api/social/imports/preview",
                     files={"file": ("weekly.csv", filedata, "text/csv")})
    assert preview.status_code == 200, preview.text
    assert preview.json()["ready_count"] == 1 and preview.json()["can_commit"] is True
    committed = mutate(client, token, "post", "/api/social/imports/commit",
                       files={"file": ("weekly.csv", filedata, "text/csv")})
    assert committed.status_code == 200 and committed.json()["created_count"] == 1
    imported = client.get("/api/social/weekly?platform=facebook").json()[0]
    assert imported["source_kind"] == "imported"
    assert imported["metrics"]["views"] is None
    assert len(imported["evidence"]) == 1
    duplicate_preview = mutate(client, token, "post", "/api/social/imports/preview",
                               files={"file": ("weekly.csv", filedata, "text/csv")})
    assert duplicate_preview.status_code == 200 and duplicate_preview.json()["error_count"] == 1
    assert duplicate_preview.json()["can_commit"] is False
    assert mutate(client, token, "post", "/api/social/imports/commit",
                  files={"file": ("weekly.csv", filedata, "text/csv")}).status_code == 422

    invalid = filedata.replace(b",12,", b",-12,")
    invalid_preview = mutate(client, token, "post", "/api/social/imports/preview",
                             files={"file": ("bad.csv", invalid, "text/csv")})
    assert invalid_preview.status_code == 200 and invalid_preview.json()["error_count"] == 1


def test_analytics_growth_quarter_approval_graph_data_and_exports(system, monkeypatch, tmp_path):
    import app.api.social as social_routes
    monkeypatch.setattr(social_routes.settings, "upload_dir", str(tmp_path))
    client, users = system
    configure_social(client, users)
    editor = client_for(); editor_token = login(editor, "editor")
    head = client_for(); head_token = login(head, "head")
    for week, day, start, end, follows, reach, views, likes in (
        ("2026-01-05", "2026-01-09", 1000, 1100, 120, 2000, 3000, 80),
        ("2026-01-12", "2026-01-16", 1100, 1200, 130, 2200, 3300, 90),
    ):
        body = weekly_body("youtube", week, reporting_date=day, audience_start=start, audience_end=end,
            new_followers=follows, lost_followers=10, reach=reach, impressions=reach * 2, views=views,
            likes=likes, comments=10, shares=10, saves=None, posts_published=3, videos_published=2)
        report = mutate(editor, editor_token, "post", "/api/social/weekly", json=body)
        assert report.status_code == 201, report.text
        assert evidence(editor, editor_token, report.json()["id"]).status_code == 201
        mutate(editor, editor_token, "post", f"/api/social/weekly/{report.json()['id']}/submit")
        assert mutate(head, head_token, "post", f"/api/social/weekly/{report.json()['id']}/review",
                      json={"decision": "approve", "comment": "Checked"}).status_code == 200

    for grain in ("week", "month", "quarter"):
        graph_data = editor.get(f"/api/social/analytics?start=2026-01-01&end=2026-03-31&grain={grain}")
        assert graph_data.status_code == 200
        assert len(graph_data.json()["series"]) == (2 if grain == "week" else 1)
        assert graph_data.json()["platform_summary"][0]["net_follower_growth"] == 200
        assert graph_data.json()["platform_summary"][0]["audience_growth_percent"] == 20.0
        if grain=="week":
            assert graph_data.json()["series"][1]["previous_period"]=="2026-01-05"
            assert graph_data.json()["series"][1]["changes_vs_previous"]["reach"]==200
    quarterly = mutate(editor, editor_token, "post", "/api/social/quarters/generate", json={"year": 2026, "quarter": 1})
    assert quarterly.status_code == 201, quarterly.text
    qid = quarterly.json()["id"]
    youtube = next(x for x in quarterly.json()["snapshot"]["platforms"] if x["platform"] == "youtube")
    assert youtube["weeks_reported"] == 2
    assert youtube["audience_start"] == 1000 and youtube["audience_end"] == 1200
    assert youtube["net_follower_growth"] == 200 and youtube["audience_growth_percent"] == 20.0
    assert youtube["reach"] == 4200 and youtube["impressions"] == 8400
    assert quarterly.json()["snapshot"]["approved_weekly_report_count"] == 2
    updated = mutate(editor, editor_token, "put", f"/api/social/quarters/{qid}", json={
        "management_notes": "Audience grew across the two approved reporting weeks; continue evidence-led publishing."})
    assert updated.status_code == 200
    assert mutate(editor, editor_token, "post", f"/api/social/quarters/{qid}/submit").status_code == 200
    assert mutate(head, head_token, "post", f"/api/social/quarters/{qid}/review",
                  json={"decision": "approve", "comment": "Quarter reviewed"}).json()["status"] == "Approved"
    approved_detail = editor.get("/api/social/quarters").json()[0]
    assert approved_detail["status"] == "Approved"
    assert mutate(editor, editor_token, "put", f"/api/social/quarters/{qid}", json={"management_notes": "alter"}).status_code == 409
    assert mutate(editor, editor_token, "post", "/api/social/quarters/generate", json={"year": 2026, "quarter": 1}).status_code == 409

    for endpoint, mime, signature in ((f"/api/social/quarters/{qid}/exports.pdf", "application/pdf", b"%PDF-"),
                                      (f"/api/social/quarters/{qid}/exports.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK")):
        result = editor.get(endpoint)
        assert result.status_code == 200 and result.headers["content-type"].startswith(mime)
        assert result.content.startswith(signature)
        if endpoint.endswith(".xlsx"):
            quarter_book=load_workbook(io.BytesIO(result.content),read_only=True)
            assert quarter_book.sheetnames==["Quarter summary","Platform results"]
            assert "Audience grew" in str(quarter_book["Quarter summary"]["B5"].value)
            quarter_book.close()
        else:
            assert result.content.rstrip().endswith(b"%%EOF")
    assert editor.get("/api/social/exports.pdf?start=2026-01-01&end=2026-01-31").content.startswith(b"%PDF-")
    weekly_xlsx = editor.get("/api/social/exports.xlsx?platform=youtube")
    assert weekly_xlsx.status_code == 200 and weekly_xlsx.content.startswith(b"PK")
    workbook = load_workbook(io.BytesIO(weekly_xlsx.content), read_only=True)
    assert workbook.active.max_row == 4
    workbook.close()
    editor.close(); head.close()
