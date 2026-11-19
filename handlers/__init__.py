# handlers/__init__.py
from handlers.common import router as common_router
from handlers.rating import router as rating_router


__all__ = ["common_router", "rating_router"]
