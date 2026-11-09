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
    path("scan/isbn/<mode:mode>/", views.isbn_scan, name="isbn_scan"),
    path("scan/qr/<mode:mode>/", views.qr_scan, name="qr_scan"),
    path("finish/", views.finish, name="finish"),
    path("cancel/", views.cancel, name="cancel"),
    path("api/book/<str:isbn>/", views.book_info, name="book_info"),
]