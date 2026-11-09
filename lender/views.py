from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


# 貸借PCの流れ: standby → isbn_scan → user_auth(QR) → finish
# ※ await は Python の予約語なので、await.html の view 名は standby にしている


def standby(request):
    return render(request, "rental/await.html")


def isbn_scan(request, mode):
    return render(request, "rental/isbn_scan.html", {"mode": mode})


def isbn_typing(request, mode):
    return render(request, "rental/isbn_typing.html", {"mode": mode})


def user_auth(request):
    return render(request, "rental/user_auth.html")


def user_auth_qr(request):
    return render(request, "rental/user_auth_qr.html")


def user_auth_typing(request):
    return render(request, "rental/user_auth_typing.html")


def finish(request):
    return render(request, "rental/finish.html")


@require_POST
def cancel(request):
    # TODO: セッションの取引情報を破棄する
    return redirect("rental:standby")