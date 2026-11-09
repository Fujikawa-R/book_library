from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


# 貸借PCの流れ: standby → isbn_scan → user_auth(QR) → finish
# ※ await は Python の予約語なので、await.html の view 名は standby にしている


def standby(request):
    return render(request, "lender/await.html")


def isbn_scan(request, mode):
    return render(request, "lender/isbn_scan.html", {"mode": mode})


def qr_scan(request, mode):
    return render(request, "lender/isbn_scan.html", {"mode": mode})


def user_auth(request):
    return render(request, "lender/user_auth.html")


def finish(request):
    return render(request, "lender/finish.html")


@require_POST
def cancel(request):
    # TODO: セッションの取引情報を破棄する
    return redirect("lender:standby")