from app.routes.calendar import router as calendar_router
from app.routes.dashboard import router as dashboard_router
from app.routes.settings import router as settings_router
from app.routes.sounds import router as sounds_router

__all__ = [
    "calendar_router",
    "dashboard_router",
    "settings_router",
    "sounds_router",
]