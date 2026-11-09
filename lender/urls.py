from django.urls import path, register_converter

from . import views

app_name = "lender"


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
    path("scan/<mode:mode>/", views.scan, name="scan"),
    path("finish/", views.finish, name="finish"),
    path("cancel/", views.cancel, name="cancel"),
]