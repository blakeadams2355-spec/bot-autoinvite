from .channel_manager import router as channel_manager_router
from .channel_settings import router as channel_settings_router
from .faq import router as faq_router
from .join_requests import router as join_requests_router
from .start import router as start_router


def get_routers():
    return [
        start_router,
        channel_manager_router,
        channel_settings_router,
        join_requests_router,
        faq_router,
    ]
