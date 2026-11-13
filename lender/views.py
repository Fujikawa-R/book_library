from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from library.models import Book

# 貸借PCの流れ: standby → isbn_scan → user_auth(QR) → finish
# ※ await は Python の予約語なので、await.html の view 名は standby にしている

SCAN_TITLES = {
    "loan": "借りたい本のISBNを読み込んでください",
    "return": "返却する本のISBNを読み込んでください",
}

def standby(request):
    return render(request, "lender/await.html")

def isbn_scan(request, mode):
    return render(request, "lender/isbn_scan.html", {
        "mode": mode,
        "page_title": SCAN_TITLES[mode],
    })

def qr_scan(request, mode):
    return render(request, "lender/qr_scan.html", {"mode": mode})

def user_auth(request, mode):
    return render(request, "lender/user_auth.html", {"mode": mode})

def finish(request):
    return render(request, "lender/finish.html")


@require_POST
def cancel(request):
    # TODO: セッションの取引情報を破棄する
    return redirect("lender:standby")


def _isbn13_ok(isbn13):
    """ISBN-13の末尾のチェックデジットが正しいか"""
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(isbn13[:12]))
    return isbn13[12] == str((10 - total % 10) % 10)


def isbn10_to_13(isbn10):
    core = "978" + isbn10[:9]
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core))
    return core + str((10 - total % 10) % 10)


def normalize_isbn(raw):
    """ハイフンや空白を除き、ISBN-13に統一する。不正なら None"""
    s = raw.replace("-", "").replace(" ", "").upper()
    if len(s) == 10 and s[:9].isdigit() and (s[9].isdigit() or s[9] == "X"):
        return isbn10_to_13(s)
    if len(s) == 13 and s.isdigit() and s[:3] in ("978", "979") and _isbn13_ok(s):
        return s
    return None


def book_info(request, isbn):
    isbn = normalize_isbn(isbn)
    if not isbn:
        return JsonResponse({"error": "ISBNの形式が正しくありません"}, status=400)

    book = Book.objects.filter(isbn=isbn).first()
    if book is None:
        return JsonResponse({"error": "この本は蔵書に登録されていません"}, status=404)

    return JsonResponse({
        "isbn": book.isbn,
        "title": book.title,
        "author": book.author,
    })