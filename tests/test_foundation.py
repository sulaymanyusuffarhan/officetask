from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_liveness_endpoint():
    response = client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_homepage_is_explicit_about_incomplete_features():
    response = client.get("/")

    assert response.status_code == 200
    assert "Foundation setup" in response.text
    assert "Do not enter employee or confidential information" in response.text
    assert "/static/images/emblem.png" in response.text
    assert "/static/images/tbc-digital-logo.jpg" in response.text


def test_original_brand_assets_are_served_locally():
    emblem = client.get("/static/images/emblem.png")
    tbc_logo = client.get("/static/images/tbc-digital-logo.jpg")

    assert emblem.status_code == 200
    assert emblem.headers["content-type"] == "image/png"
    assert len(emblem.content) > 100_000
    assert tbc_logo.status_code == 200
    assert tbc_logo.headers["content-type"] == "image/jpeg"
    assert len(tbc_logo.content) > 10_000
