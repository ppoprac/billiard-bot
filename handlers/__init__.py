# handlers/__init__.py
from handlers.common import router as common_router
from handlers.rating import router as rating_router
from handlers.matches import router as matches_router
from handlers.challenges import router as challenges_router
from handlers.admin import router as admin_router


__all__ = [
    "common_router",
    "rating_router",
    "matches_router",
    "challenges_router",
    "admin_router",
]
