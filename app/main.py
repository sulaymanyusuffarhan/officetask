from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import engine


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Private, LAN-hosted office task and performance management system.",
    docs_url="/api/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    """Serve the honest project foundation page; authenticated workflows come later."""
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Indicate that the application process is running (no database dependency)."""
    return {"status": "alive"}


@app.get("/api/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    """Check the database connection before deployment traffic is sent to this instance."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ready", "database": "available"}
