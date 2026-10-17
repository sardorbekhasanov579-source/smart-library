"""Joriy foydalanuvchini oqim (thread) darajasida saqlovchi middleware."""
import threading

_state = threading.local()


def get_current_user():
    return getattr(_state, "user", None)


class CurrentUserMiddleware:
    """Modellar ichidan joriy foydalanuvchini olish imkonini beradi (audit uchun)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.user = getattr(request, "user", None)
        try:
            response = self.get_response(request)
        finally:
            _state.user = None
        return response
