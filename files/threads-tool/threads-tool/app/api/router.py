from fastapi import APIRouter

from app.api.routes import accounts, analytics, auth, proxies, publish, radar, sources

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(sources.router)
api_router.include_router(analytics.router)
api_router.include_router(proxies.router)
api_router.include_router(publish.router)
api_router.include_router(radar.router)
