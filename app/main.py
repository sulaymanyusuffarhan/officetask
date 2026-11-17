from pathlib import Path
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.db.session import engine
from app.api.routes import router as api_router
from app.api.export_routes import router as report_router
from app.api.analytics import router as analytics_router
from app.api.equipment import router as equipment_router
from app.api.social import router as social_router


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Private, LAN-hosted office task and performance management system.",
    docs_url="/api/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)


@app.exception_handler(IntegrityError)
async def integrity_conflict(_request: Request, _exc: IntegrityError):
    return JSONResponse({"detail": "Record conflicts with existing data; refresh and try again."}, status_code=409)


def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
    if settings.app_env.lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        expected = request.session.get("csrf_token")
        supplied = request.headers.get("x-csrf-token")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            return security_headers(JSONResponse({"detail": "CSRF validation failed"}, status_code=403))
    response = await call_next(request)
    return security_headers(response)


# Session middleware wraps CSRF middleware so the CSRF checker reads the session cookie.
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="officetask_session",
                   max_age=settings.session_max_age_seconds, same_site="strict",
                   https_only=settings.app_env.lower() == "production")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(api_router)
app.include_router(report_router)
app.include_router(analytics_router)
app.include_router(equipment_router)
app.include_router(social_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/api/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ready", "database": "available"}
