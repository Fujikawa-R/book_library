from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from accounts.models import User


def is_admin(user):
    """管理者（role=admin）またはスーパーユーザーなら True。"""
    return user.is_authenticated and (
        user.role == User.Role.ADMIN or user.is_superuser
    )


def admin_required(view_func):
    """管理者専用ビュー用。
    未ログインならログイン画面へリダイレクトし、
    ログイン済みでも管理者でなければ 403 を返す。"""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)
