from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.repository import JsonRepository
from app.api.router import router
from app.core.config import Settings, settings
from app.core.errors import AppError
from app.services.runtime import TutorRuntime


def create_app(config: Settings | None = None) -> FastAPI:
    active = config or settings

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = TutorRuntime(active, JsonRepository(active.runtime_dir))
        yield

    app = FastAPI(
        title=active.app_name,
        version="0.1.0",
        description="Deterministic, evidence-backed adaptive tutoring prototype.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
        trace_id = getattr(getattr(request.app.state, "runtime", None), "_id", lambda _: None)("tr")
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "retryable": error.retryable,
                    "trace_id": trace_id,
                    "details": error.details,
                }
            },
        )

    app.include_router(router)
    return app


app = create_app()

