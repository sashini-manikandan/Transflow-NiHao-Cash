"""BillWise AI - FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import SessionLocal, create_all
from .routers import actions, assistant, insights, meta, transactions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("billwise")

DESCRIPTION = """\
Financial obligations assistant for international students.

All data served by this API is **synthetic demo data**. No bank is connected,
no real credentials are stored, and all exchange rates are simulated and
labelled as such.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    create_all()
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            created = __import__(
                "app.seed.seed_data", fromlist=["seed_if_empty"]
            ).seed_if_empty(db, email=settings.demo_user_email)
            logger.info("startup seed: %s", "created demo data" if created else "already present")
        except Exception:
            logger.exception("startup seeding failed")
            db.rollback()
        finally:
            db.close()
    logger.info(
        "assistant mode: %s",
        "llm" if settings.llm_enabled else "offline_deterministic (no API key set)",
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BillWise AI",
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Demo-User"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        """Return field-level messages without echoing the whole payload back."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Request validation failed.",
                "errors": [
                    {
                        "field": ".".join(str(p) for p in err.get("loc", ())[1:]) or "body",
                        "message": err.get("msg", "invalid value"),
                    }
                    for err in exc.errors()[:10]
                ],
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        """Never leak a stack trace, SQL, or configuration to the client."""
        logger.exception("unhandled error path=%s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Something went wrong handling that request."},
        )

    for module in (meta, transactions, insights, actions, assistant):
        app.include_router(module.router)

    return app


app = create_app()
