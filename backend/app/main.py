import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.tickets import router as tickets_router
from app.api.routers.resolutions import router as resolutions_router
from app.api.routers.mcp import router as mcp_router
from app.api.routers.users import router as users_router
from app.api.routers.orchestrator import router as orchestrator_router
from app.api.routers.kb import router as kb_router
from app.api.routers.manager import router as manager_router

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
    app.include_router(kb_router)
    app.include_router(manager_router)

    d365_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "d365")
    if os.path.isdir(d365_dir):
        app.mount("/d365", StaticFiles(directory=d365_dir), name="d365")

    return app

app = create_app()