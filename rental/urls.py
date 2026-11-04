from django.urls import path, register_converter

from . import views

app_name = "rental"


class ModeConverter:
    """貸出(loan)と返却(return)だけを URL として通す。"""
    regex = "loan|return"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(ModeConverter, "mode")

urlpatterns = [
    path("", views.standby, name="standby"),
    path("isbn/<mode:mode>/", views.isbn_scan, name="isbn_scan"),
    path("isbn/<mode:mode>/typing/", views.isbn_typing, name="isbn_typing"),
    path("auth/", views.user_auth, name="user_auth"),
    path("auth/qr/", views.user_auth_qr, name="user_auth_qr"),
    path("auth/typing/", views.user_auth_typing, name="user_auth_typing"),
    path("finish/", views.finish, name="finish"),
    path("cancel/", views.cancel, name="cancel"),
]