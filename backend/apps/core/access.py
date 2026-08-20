from apps.accounts.models import UserProfile


def is_tenant_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    if not profile:
        return False
        
    if profile.profile_type in (UserProfile.PROFILE_ADMIN, UserProfile.PROFILE_OWNER):
        return True
        
    return bool(profile.role_id and profile.role.is_account_admin)
