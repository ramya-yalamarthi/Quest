from fastapi import FastAPI
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.tickets import router as tickets_router

def create_app() -> FastAPI:
    app = FastAPI(title="Support AI Backend", version="0.2.0")

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(tickets_router)

    return app

app = create_app()