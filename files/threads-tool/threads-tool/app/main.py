from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.db.indexes import ensure_indexes, ensure_timeseries
from app.db.mongo import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    await ensure_timeseries()
    yield
    await close_client()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.environment}
