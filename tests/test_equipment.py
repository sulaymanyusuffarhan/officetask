from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import login, mutate


def upload_equipment_photo(client, token, asset_id):
    return mutate(client, token, "post", f"/api/equipment/assets/{asset_id}/photo",
                  files={"file": ("equipment.jpg", b"\xff\xd8\xffequipment-photo", "image/jpeg")})


def test_shift_custodian_issue_handover_partial_return_and_traceability(system, monkeypatch, tmp_path):
    client, users = system
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.equipment as equipment_routes
    monkeypatch.setattr(equipment_routes.settings, "upload_dir", str(tmp_path))
    head_client=client
    editor_client=TestClient(app)
    morning_client=TestClient(app)
    evening_client=TestClient(app)
    work_date = datetime.now(ZoneInfo("Africa/Dar_es_Salaam")).date()
    head_token = login(head_client, "head")
    editor_token = login(editor_client, "editor")
    morning_token = login(morning_client, "employee")
    evening_token = login(evening_client, "leader")
    policy = mutate(head_client, head_token, "put", "/api/equipment/authorization-roles",
                    json={"roles": ["head_of_office", "editor"]})
    assert policy.status_code == 200

    assets = {}
    for tag, name, category in [
        ("CAM-001", "Canon EOS 200D body", "Camera"),
        ("LEN-001", "18-55mm lens", "Lens"),
        ("BAT-001", "Camera battery", "Battery"),
        ("CHG-001", "Camera charger", "Charger"),
    ]:
        created = mutate(head_client, head_token, "post", "/api/equipment/assets", json={
            "asset_tag": tag, "category": category, "name": name, "brand": "Canon",
            "model": "EOS 200D kit", "serial_number": None, "condition": "Good"})
        assert created.status_code == 201, created.text
        assets[tag] = created.json()["id"]
    no_photo = mutate(editor_client, editor_token, "post", "/api/equipment/requests", json={
        "asset_ids": [assets["CAM-001"]], "borrower_name": "Editor", "borrower_office": "News desk",
        "shift_id": users["morning"], "shift_date": work_date.isoformat(),
        "expected_return_at": (datetime.utcnow()+timedelta(hours=4)).isoformat(), "purpose": "Test missing photo"})
    assert no_photo.status_code == 422 and "photograph" in no_photo.text
    for asset_id in assets.values():
        assert upload_equipment_photo(head_client, head_token, asset_id).status_code == 200
    for tag in ("LEN-001", "BAT-001", "CHG-001"):
        linked = mutate(head_client, head_token, "post", f"/api/equipment/assets/{assets['CAM-001']}/accessories",
                        json={"accessory_asset_id": assets[tag]})
        assert linked.status_code == 201, linked.text

    for shift_id, custodian_id in ((users["morning"], users["employee"]), (users["evening"], users["leader"])):
        assigned = mutate(head_client, head_token, "post", "/api/equipment/custodians", json={
            "shift_id": shift_id, "custodian_id": custodian_id, "effective_from": work_date.isoformat(),
            "reason": "Equipment room roster"})
        assert assigned.status_code == 201, assigned.text

    request = mutate(editor_client, editor_token, "post", "/api/equipment/requests", json={
        "asset_ids": [assets["CAM-001"]], "borrower_id": users["editor"], "borrower_name": "Editor",
        "borrower_office": "News desk", "external": False, "shift_id": users["morning"],
        "shift_date": work_date.isoformat(), "expected_return_at": (datetime.utcnow()+timedelta(hours=4)).isoformat(),
        "purpose": "Field reporting"})
    assert request.status_code == 201, request.text
    issue_id = request.json()["id"]
    assert {a["asset_tag"] for a in request.json()["items"]} == set(assets)

    not_yet = mutate(morning_client, morning_token, "post", f"/api/equipment/requests/{issue_id}/issue",
                     json={"conditions": {str(x): "Good" for x in assets.values()}})
    assert not_yet.status_code == 409, not_yet.text

    authorized = mutate(head_client, head_token, "post", f"/api/equipment/requests/{issue_id}/authorize",
                        json={"method": "Head of Office authorization", "remarks": "Approved for field assignment"})
    assert authorized.status_code == 200
    assert authorized.json()["authorized_by_id"] == users["head"]

    issued = mutate(morning_client, morning_token, "post", f"/api/equipment/requests/{issue_id}/issue",
                    json={"conditions": {str(x): "Good" for x in assets.values()}})
    assert issued.status_code == 200, issued.text
    assert issued.json()["issued_by_id"] == users["employee"]

    acknowledged = mutate(editor_client, editor_token, "post", f"/api/equipment/requests/{issue_id}/acknowledge",
                          json={"acknowledged": True})
    assert acknowledged.status_code == 200
    assert acknowledged.json()["borrower_acknowledged_by_id"] == users["editor"]

    handover = mutate(morning_client, morning_token, "post", "/api/equipment/handovers", json={
        "outgoing_shift_id": users["morning"], "incoming_shift_id": users["evening"],
        "shift_date": work_date.isoformat(), "outgoing_custodian_id": users["employee"],
        "incoming_custodian_id": users["leader"], "discrepancies": "Four assets remain with borrower"})
    assert handover.status_code == 201, handover.text
    assert len(handover.json()["outstanding_items"]) == 4
    mutate(morning_client, morning_token, "post", f"/api/equipment/handovers/{handover.json()['id']}/acknowledge", json={})
    accepted_handover = mutate(evening_client, evening_token, "post",
        f"/api/equipment/handovers/{handover.json()['id']}/acknowledge", json={})
    assert accepted_handover.status_code == 200
    assert len(accepted_handover.json()["outstanding_items"]) == 4
    assert accepted_handover.json()["outstanding_items"][0]["borrower_name"] == "Editor"
    incoming_view = evening_client.get("/api/equipment/requests")
    assert any(x["id"] == issue_id and x["outstanding_count"] == 4 for x in incoming_view.json())
    # Shift custody transfer records accountability only; it does not return borrowed items.
    assert accepted_handover.json()["outstanding_items"]

    returned = mutate(evening_client, evening_token, "post", f"/api/equipment/requests/{issue_id}/return", json={
        "shift_id": users["evening"], "shift_date": work_date.isoformat(),
        "returned": [
            {"asset_id": assets["CAM-001"], "condition": "Good", "damage_notes": ""},
            {"asset_id": assets["LEN-001"], "condition": "Good", "damage_notes": ""},
            {"asset_id": assets["BAT-001"], "condition": "Damaged", "damage_notes": "Battery casing cracked"},
        ],
        "missing_asset_ids": [assets["CHG-001"]], "notes": "Charger absent at return"})
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "Partially returned"
    assert returned.json()["outstanding_count"] == 1
    charger = next(x for x in returned.json()["items"] if x["asset_tag"] == "CHG-001")
    assert charger["returned_at"] is None and charger["missing_reported"] is True

    history = head_client.get(f"/api/equipment/reports/assets/{assets['CHG-001']}/history")
    assert history.status_code == 200
    event_types = [e["event_type"] for e in history.json()["events"]]
    assert "issued" in event_types and "missing_reported" in event_types
    report = head_client.get("/api/equipment/reports/missing")
    assert report.status_code == 200 and report.json()[0]["asset_tag"] == "CHG-001"
    damaged = next(x for x in head_client.get("/api/equipment/assets").json() if x["asset_tag"] == "BAT-001")
    assert damaged["availability"] == "Damaged"
    bypass = mutate(head_client, head_token, "patch", f"/api/equipment/assets/{assets['BAT-001']}", json={"condition": "Good"})
    assert bypass.status_code == 409
    inspected = mutate(head_client, head_token, "post", f"/api/equipment/assets/{assets['BAT-001']}/inspect",
                       json={"condition": "Fair", "disposition": "Maintenance", "notes": "Sent for battery safety inspection"})
    assert inspected.status_code == 200 and inspected.json()["availability"] == "Maintenance"
    head_view = head_client.get(f"/api/equipment/requests")
    assert head_view.status_code == 200
    trace = next(r for r in head_view.json() if r["id"] == issue_id)
    assert trace["authorized_by_id"] == users["head"]
    assert trace["issued_by_id"] == users["employee"]
    assert trace["borrower_id"] == users["editor"]
    missing_item = next(x for x in trace["items"] if x["asset_tag"] == "CHG-001")
    assert missing_item["received_by_id"] is None and missing_item["returned_at"] is None
    returned_assets = [x for x in trace["items"] if x["returned_at"]]
    assert all(x["received_by_id"] == users["leader"] for x in returned_assets)
    editor_client.close(); morning_client.close(); evening_client.close()


def test_equipment_authorization_roles_and_asset_tag_security(system, monkeypatch, tmp_path):
    client, users = system
    staff_token = login(client, "employee")
    denied = mutate(client, staff_token, "post", "/api/equipment/assets", json={
        "asset_tag": "MIC-009", "category": "Microphone", "name": "Field microphone"})
    assert denied.status_code == 403
    head_token = login(client, "head")
    asset = mutate(client, head_token, "post", "/api/equipment/assets", json={
        "asset_tag": "MIC-009", "category": "Microphone", "name": "Field microphone", "serial_number": ""})
    assert asset.status_code == 201 and asset.json()["serial_number"] is None
    duplicate = mutate(client, head_token, "post", "/api/equipment/assets", json={
        "asset_tag": "MIC-009", "category": "Microphone", "name": "Duplicate asset"})
    assert duplicate.status_code == 409
    qr = client.get(f"/api/equipment/assets/{asset.json()['id']}/qr.svg")
    assert qr.status_code == 200 and "<svg" in qr.text
    import app.api.equipment as equipment_routes
    monkeypatch.setattr(equipment_routes.settings, "upload_dir", str(tmp_path))
    photo = mutate(client, head_token, "post", f"/api/equipment/assets/{asset.json()['id']}/photo",
                   files={"file": ("front.jpg", b"\xff\xd8\xffphoto-bytes", "image/jpeg")})
    assert photo.status_code == 200
    download = client.get(f"/api/equipment/assets/{asset.json()['id']}/photo")
    assert download.status_code == 200 and download.content.startswith(b"\xff\xd8\xff")


def test_external_borrowing_delegated_authorization_and_absence_replacement(system, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.equipment as equipment_routes

    head_client, users = system
    monkeypatch.setattr(equipment_routes.settings, "upload_dir", str(tmp_path))
    editor_client=TestClient(app); authorizer_client=TestClient(app); original_client=TestClient(app); replacement_client=TestClient(app)
    day=datetime.now(ZoneInfo("Africa/Dar_es_Salaam")).date()
    head_token=login(head_client,"head")
    assert mutate(head_client,head_token,"put","/api/equipment/authorization-roles",json={"roles":["shift_leader"]}).status_code==200
    asset=mutate(head_client,head_token,"post","/api/equipment/assets",json={"asset_tag":"REC-001","category":"Recorder","name":"Audio recorder"}).json()
    assert upload_equipment_photo(head_client,head_token,asset["id"]).status_code==200
    for shift,user in ((users["morning"],users["employee"]),(users["morning"],users["employee2"])):
        response=mutate(head_client,head_token,"post","/api/equipment/custodians",json={"shift_id":shift,"custodian_id":user,"effective_from":day.isoformat(),"reason":"Roster"})
        assert response.status_code==201,response.text
    replacement=mutate(head_client,head_token,"post","/api/equipment/custodians/replacements",json={
        "shift_id":users["morning"],"shift_date":day.isoformat(),"original_custodian_id":users["employee"],
        "replacement_custodian_id":users["employee2"],"reason":"Original custodian on approved leave"})
    assert replacement.status_code==201,replacement.text
    editor_token=login(editor_client,"editor")
    request=mutate(editor_client,editor_token,"post","/api/equipment/requests",json={
        "asset_ids":[asset["id"]],"borrower_name":"External Operator","borrower_office":"District Radio",
        "external":True,"shift_id":users["morning"],"shift_date":day.isoformat(),
        "expected_return_at":(datetime.utcnow()+timedelta(hours=3)).isoformat(),"purpose":"Joint field coverage"})
    assert request.status_code==201,request.text
    issue_id=request.json()["id"]
    authorizer_token=login(authorizer_client,"leader")
    allowed=mutate(authorizer_client,authorizer_token,"post",f"/api/equipment/requests/{issue_id}/authorize",
                   json={"method":"Other delegated authorization","remarks":"Delegated shift approval"})
    assert allowed.status_code==200 and allowed.json()["authorized_role_id"]=="shift_leader"
    original_token=login(original_client,"employee")
    denied=mutate(original_client,original_token,"post",f"/api/equipment/requests/{issue_id}/issue",json={"conditions":{str(asset["id"]):"Good"}})
    assert denied.status_code==403
    replacement_token=login(replacement_client,"employee2")
    issued=mutate(replacement_client,replacement_token,"post",f"/api/equipment/requests/{issue_id}/issue",json={"conditions":{str(asset["id"]):"Good"}})
    assert issued.status_code==200 and issued.json()["issued_by_id"]==users["employee2"]
    ack=mutate(replacement_client,replacement_token,"post",f"/api/equipment/requests/{issue_id}/acknowledge",json={
        "acknowledged":True,"borrower_name":"External Operator"})
    assert ack.status_code==200 and ack.json()["borrower_acknowledged_name"]=="External Operator"
    head_client.close();editor_client.close();authorizer_client.close();original_client.close();replacement_client.close()
