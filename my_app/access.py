from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied


ADMINISTRATOR = "administrator"
OFFICE_STAFF = "office_staff"
TEACHER = "teacher"
PARENT = "parent"
STUDENT = "student"


def role_for(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ADMINISTRATOR
    try:
        profile = user.school_profile
    except ObjectDoesNotExist:
        return None
    return profile.role


def role_required(*allowed_roles):
    def decorate(view):
        @login_required
        @wraps(view)
        def guarded(request, *args, **kwargs):
            role = role_for(request.user)
            if role is None:
                raise PermissionDenied
            if role != ADMINISTRATOR and role not in allowed_roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return guarded

    return decorate


def school_role_context(request):
    if not request.user.is_authenticated:
        return {"school_role": None}
    from .models import AcademicYear

    return {
        "school_role": role_for(request.user),
        "current_year": AcademicYear.objects.filter(is_current=True).first(),
    }
