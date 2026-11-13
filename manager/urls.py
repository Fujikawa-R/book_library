from django.urls import path

from . import views

app_name = "manager"

urlpatterns = [
    # 図書
    path("books/", views.book_list, name="book_list"),
    path("books/add/", views.book_add, name="book_add"),
    path("books/<str:isbn>/", views.book_detail, name="book_detail"),
    path("books/<str:isbn>/suspend/", views.book_suspend_toggle, name="book_suspend_toggle"),
    path("books/<str:isbn>/lost/", views.book_lost, name="book_lost"),
    # 利用者
    path("users/", views.user_list, name="user_list"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("users/<int:user_id>/deactivate/", views.user_deactivate, name="user_deactivate"),
    path("users/<int:user_id>/extend/", views.user_extend_graduation, name="user_extend_graduation"),
    path("users/<int:user_id>/extend/cancel/", views.user_cancel_extension, name="user_cancel_extension"),
    # 学科
    path("departments/", views.department_list, name="department_list"),
    path("departments/<int:department_id>/deactivate/", views.department_deactivate, name="department_deactivate"),
    # 貸出状況
    path("rentals/", views.rental_list, name="rental_list"),
    path("rentals/<int:rental_id>/", views.rental_detail, name="rental_detail"),
    # 評価の通報
    path("reports/", views.report_list, name="report_list"),
    path("reports/<int:report_id>/", views.report_detail, name="report_detail"),
    path("reports/<int:report_id>/delete-review/", views.report_delete_review, name="report_delete_review"),
    # 通知
    path("notices/", views.notice_list, name="notice_list"),
    path("user-notices/", views.user_notice_list, name="user_notice_list"),
    path("user-notices/texts/", views.user_notice_text_list, name="user_notice_text_list"),
]