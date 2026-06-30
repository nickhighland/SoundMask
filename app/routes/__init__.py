from app.routes.calendar import router as calendar_router
from app.routes.calendar_view import router as calendar_view_router
from app.routes.dashboard import router as dashboard_router
from app.routes.settings import router as settings_router
from app.routes.sounds import router as sounds_router
from app.routes.updates import router as updates_router

__all__ = [
    "calendar_router",
    "calendar_view_router",
    "dashboard_router",
    "settings_router",
    "sounds_router",
    "updates_router",
]
