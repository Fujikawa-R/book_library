from django.shortcuts import redirect, render


# TODO: 実装が進んだら、ログイン必須（@login_required）と処理を追加する


def mypage(request):
    return render(request, "phone/mypage.html")


def setting(request):
    return render(request, "phone/setting.html")


def book_search(request):
    return render(request, "phone/book_search.html")


def book_detail(request, isbn):
    return render(request, "phone/book_detail.html", {"isbn": isbn})


def review_update(request, isbn):
    # 評価の投稿・編集を受け取り、図書詳細へ戻る
    return redirect("phone:book_detail", isbn=isbn)


def review_report(request, review_id):
    return render(request, "phone/review_report.html", {"review_id": review_id})


def isbn_scan(request):
    return render(request, "phone/isbn_scan.html")


def isbn_typing(request):
    return render(request, "phone/isbn_typing.html")