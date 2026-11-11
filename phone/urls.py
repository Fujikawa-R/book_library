from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

app_name = "phone"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="registration/phone_login.html"), name="login"),
    path("logout/",auth_views.LogoutView.as_view(template_name="registration/phone_logged_out.html"),name="logout"),
    path("mypage/", views.mypage, name="mypage"),
    path("setting/", views.setting, name="setting"),
    path("books/", views.book_search, name="book_search"),
    path("books/<str:isbn>/", views.book_detail, name="book_detail"),
    path("books/<str:isbn>/review/", views.review_update, name="review_update"),
    path("reviews/<int:review_id>/report/", views.review_report, name="review_report"),
    path("isbn/scan/", views.isbn_scan, name="isbn_scan"),
    path("isbn/typing/", views.isbn_typing, name="isbn_typing"),
    path("signup/", views.signup, name="signup"),
]