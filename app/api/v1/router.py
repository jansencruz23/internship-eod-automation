from fastapi import APIRouter

from app.api.v1.endpoints import activities, reports, pages

api_router = APIRouter()
api_router.include_router(activities.router, prefix="/activities", tags=["activities"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(pages.router, tags=["pages"])
