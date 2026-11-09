
from django.http import Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q, Avg

from library.models import Book, Rental, Review


# TODO: 実装が進んだら、ログイン必須（@login_required）と処理を追加する


def mypage(request):
    return render(request, "phone/mypage.html")

def setting(request):
    student = {
        "student_id": "4253111",
        "email": "example@morijyobi.ac.jp",
        "department": "情報システム科",
    }

    departments = [
        "情報システム科",
        "高度情報工学科",
        "ネットワークセキュリティ科",
        "ゲームクリエイター科",
    ]

    return render(request, "phone/setting.html", {
        "student": student,
        "departments": departments,
    })


# student.student_id	学籍番号
# student.email	        メールアドレス
# student.department	学科
# departments	        学科の選択肢


def book_search(request):
    books = Book.objects.filter(is_suspended=False)

    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "rating")

    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query)
        )

    # データベースから取得した本に評価と在庫数を追加
    books = list(books)

    for book in books:
        book.rating = Review.objects.filter(
            book=book,
            is_active=True
        ).aggregate(average=Avg("point"))["average"]

        rental_count = Rental.objects.filter(
            book=book,
            return_date__isnull=True,
            is_lost=False
        ).count()

        book.stock = max(0, book.total_copies - rental_count)

    if sort == "rating":
        books.sort(
            key=lambda book: book.rating if book.rating is not None else -1,
            reverse=True
        )

    elif sort == "stock":
        books.sort(
            key=lambda book: book.stock,
            reverse=True
        )

    context = {
        "books": books,
        "query": query,
        "sort": sort,
    }

    return render(request, "phone/book_search.html", context)

def book_detail(request, isbn):
    book = get_object_or_404(
        Book,
        isbn=isbn,
        is_suspended=False
    )

    reviews = Review.objects.filter(
        book=book,
        is_active=True
    ).select_related("student")

    book.rating = reviews.aggregate(
        average=Avg("point")
    )["average"]

    rental_count = Rental.objects.filter(
        book=book,
        return_date__isnull=True,
        is_lost=False
    ).count()

    book.stock = max(0, book.total_copies - rental_count)

    return render(request, 'phone/book_detail.html', {
        'book': book,
        'my_review': None,
        'reviews': reviews,
    })

def review_update(request, isbn):
    # 評価の投稿・編集を受け取り、図書詳細へ戻る
    return redirect("phone:book_detail", isbn=isbn)


def review_report(request, review_id):
    return render(request, "phone/review_report.html", {"review_id": review_id})


def isbn_scan(request):
    return render(request, "phone/isbn_scan.html")


def isbn_typing(request):
    return render(request, "phone/isbn_typing.html")
