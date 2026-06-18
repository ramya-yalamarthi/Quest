import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.tickets import router as tickets_router
from app.api.routers.resolutions import router as resolutions_router
from app.api.routers.mcp import router as mcp_router
from app.api.routers.users import router as users_router
from app.api.routers.orchestrator import router as orchestrator_router
from app.mitigation_safety import (
    on_shutdown as ms_on_shutdown,
    on_startup as ms_on_startup,
    register_router as register_mitigation_safety_router,
)

def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    app = FastAPI(title="Support AI Backend", version="0.2.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(tickets_router)
    app.include_router(resolutions_router)
    app.include_router(mcp_router)
    app.include_router(users_router)
    app.include_router(orchestrator_router)
    app.include_router(register_mitigation_safety_router())

    app.add_event_handler("startup", ms_on_startup)
    app.add_event_handler("shutdown", ms_on_shutdown)

    return app

app = create_app()