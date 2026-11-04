from django.urls import path

from . import views

app_name = "phone"

urlpatterns = [
    path("mypage/", views.mypage, name="mypage"),
    path("setting/", views.setting, name="setting"),
    path("books/", views.book_search, name="book_search"),
    path("books/<str:isbn>/", views.book_detail, name="book_detail"),
    path("books/<str:isbn>/review/", views.review_update, name="review_update"),
    path("reviews/<int:review_id>/report/", views.review_report, name="review_report"),
    path("isbn/scan/", views.isbn_scan, name="isbn_scan"),
    path("isbn/typing/", views.isbn_typing, name="isbn_typing"),
]