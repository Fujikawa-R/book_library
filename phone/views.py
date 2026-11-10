from django.http import Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q, Avg
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from accounts.models import User
from library.models import Book, Rental, Review
from accounts.models import Student, Department


# TODO: 実装が進んだら、ログイン必須（@login_required）と処理を追加する


def mypage(request):
    return render(request, "phone/mypage.html")

@login_required
def setting(request):
    student = get_object_or_404(
        Student.objects.select_related("user", "department"),
        user=request.user
    )

    departments = Department.objects.filter(is_active=True)

    error = None
    success = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        department_id = request.POST.get("department", "")

        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        department = Department.objects.filter(
            id=department_id,
            is_active=True
        ).first() if department_id.isdigit() else None

        if not email:
            error = "メールアドレスを入力してください。"

        elif User.objects.filter(email__iexact=email).exclude(
            pk=request.user.pk
        ).exists():
            error = "このメールアドレスは既に使用されています。"

        elif department is None:
            error = "正しい学科を選択してください。"

        elif current_password or new_password or confirm_password:
            if not all([current_password, new_password, confirm_password]):
                error = "パスワード変更欄をすべて入力してください。"

            elif not request.user.check_password(current_password):
                error = "現在のパスワードが正しくありません。"

            elif new_password != confirm_password:
                error = "新しいパスワードが一致しません。"

            else:
                try:
                    validate_password(new_password, request.user)
                except ValidationError as e:
                    error = " ".join(e.messages)

        if error is None:
            try:
                with transaction.atomic():
                    request.user.email = email

                    if new_password:
                        request.user.set_password(new_password)

                    request.user.save()

                    student.department = department
                    student.save(update_fields=["department"])

                if new_password:
                    update_session_auth_hash(request, request.user)

                return redirect("phone:setting")

            except Exception:
                error = "保存に失敗しました。もう一度お試しください。"

    return render(request, "phone/setting.html", {
        "student": student,
        "departments": departments,
        "error": error,
        "success": success,
    })

def book_search(request):
    books = Book.objects.filter(is_suspended=False)

    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "rating")

    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query)
        )

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

    return render(request, "phone/book_search.html", {
        "books": books,
        "query": query,
        "sort": sort,
    })

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
