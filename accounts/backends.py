from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Allows users to log in with either their username or their email address.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get("email")
        if not username or not password:
            return None

        clean_user = username.strip()

        try:
            # Match either username or email case-insensitively
            user = User.objects.filter(
                Q(username__iexact=clean_user) | Q(email__iexact=clean_user)
            ).first()
        except User.DoesNotExist:
            return None

        if user and (user.check_password(password) or user.check_password(password.strip())) and self.user_can_authenticate(user):
            return user
        return None
