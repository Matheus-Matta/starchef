from apps.accounts.models import UserProfile


def is_tenant_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    return bool(profile and profile.profile_type == UserProfile.PROFILE_ADMIN)
