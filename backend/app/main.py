from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.tickets import router as tickets_router
from app.api.routers.resolutions import router as resolutions_router
from app.api.routers.mcp import router as mcp_router

def create_app() -> FastAPI:
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

    return app

app = create_app()