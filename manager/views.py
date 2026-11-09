from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


# TODO: 実装が進んだら、管理者のみ許可する（@staff_member_required など）


def book_list(request):
    return render(request, "manager/book_list.html")


def add_book(request):
    return render(request, "manager/add_book.html")


def book_detail(request, isbn):
    return render(request, "manager/book_detail.html", {"isbn": isbn})


def user_list(request):
    return render(request, "manager/user_list.html")


def user_detail(request, user_id):
    return render(request, "manager/user_detail.html", {"user_id": user_id})


def department_list(request):
    return render(request, "manager/department_list.html")


def rental_list(request):
    return render(request, "manager/rental_list.html")


def rental_detail(request, loan_id):
    return render(request, "manager/rental_detail.html", {"rental_id": loan_id})


def report_list(request):
    return render(request, "manager/report_list.html")


def report_detail(request, report_id):
    return render(request, "manager/report_detail.html", {"report_id": report_id})


def notice_list(request):
    return render(request, "manager/notice_list.html")


def user_notice_list(request):
    return render(request, "manager/user_notice_list.html")


def user_notice_text_list(request):
    return render(request, "manager/user_notice_text_list.html")


@require_POST
def book_suspend_toggle(request, isbn):
    # TODO: 貸出停止・解除
    return redirect("manager:book_detail", isbn=isbn)


@require_POST
def book_lost(request, isbn):
    # TODO: 紛失処理（冊数を減らす）
    return redirect("manager:book_detail", isbn=isbn)


@require_POST
def user_deactivate(request, user_id):
    # TODO: 手動の無効化
    return redirect("manager:user_detail", user_id=user_id)


@require_POST
def user_extend_graduation(request, user_id):
    # TODO: 卒業年の延長
    return redirect("manager:user_detail", user_id=user_id)


@require_POST
def department_deactivate(request, department_id):
    # TODO: 学科の無効化（アクティブな生徒がいないときのみ）
    return redirect("manager:department_list")


@require_POST
def report_delete_review(request, report_id):
    # TODO: 通報された評価の削除
    return redirect("manager:report_detail", report_id=report_id)