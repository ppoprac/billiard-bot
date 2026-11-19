# handlers/__init__.py
from handlers.common import router as common_router
from handlers.rating import router as rating_router
from handlers.matches import router as matches_router


__all__ = ["common_router", "rating_router", "matches_router"]
