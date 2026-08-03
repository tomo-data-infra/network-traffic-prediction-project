import jwt
from django.conf import settings
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrReadOnly(BasePermission):
    """Allows unauthenticated reads; write methods require a valid admin JWT."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False

        token = auth_header[len("Bearer "):]
        try:
            jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return False

        return True
