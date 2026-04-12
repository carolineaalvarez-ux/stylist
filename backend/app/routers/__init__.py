from .matches import router as matches_router
from .products import router as products_router
from .feedback import router as feedback_router
from .alerts import router as alerts_router
from .scraper import router as scraper_router

__all__ = [
    "matches_router",
    "products_router",
    "feedback_router",
    "alerts_router",
    "scraper_router",
]
