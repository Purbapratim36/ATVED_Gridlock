from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import uuid
import structlog

from atved.config import get_settings
from atved.db.session import init_db, dispose_engine

logger = structlog.get_logger(__name__)

# Request ID Middleware
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting ATVED API", version=app.version)
    
    # In development, auto-create tables
    settings = get_settings()
    if settings.app.debug:
        logger.info("Initializing database (dev mode)")
        await init_db()
        
    yield
    
    # Shutdown
    logger.info("Shutting down ATVED API")
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app.name,
        description=settings.app.description,
        version=settings.app.version,
        lifespan=lifespan,
    )

    # Middlewares
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health endpoint (no auth)
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": settings.app.version}

    # Routers
    from atved.api.routers import auth, camera, violation, analytics, driver, ingest
    
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.include_router(camera.router, prefix="/api/v1")
    app.include_router(violation.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")
    app.include_router(driver.router, prefix="/api/v1")
    app.include_router(ingest.router, prefix="/api/v1")

    return app
