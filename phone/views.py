from django.shortcuts import redirect, render


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
    # 仮の書籍データ
    books = [
        {
            "id": 1,
            "title": "Java基礎",
            "description": "プログラミング入門",
            "rating": 4.4,
            "stock": 2,
            "tags": ["Java", "プログラミング"],
        },
        {
            "id": 2,
            "title": "Java応用",
            "description": "ステップアップ学習",
            "rating": 3.4,
            "stock": 5,
            "tags": ["Java", "応用"],
        },
        {
            "id": 3,
            "title": "JavaScript",
            "description": "Web開発の基礎",
            "rating": 0.4,
            "stock": 0,
            "tags": ["JavaScript", "Web"],
        },
    ]

    # 検索キーワード
    query = request.GET.get("q", "").strip()

    # 並び替え条件
    sort = request.GET.get("sort", "rating")

    # タイトル・説明文で検索
    if query:
        books = [
            book for book in books
            if query.lower() in book["title"].lower()
            or query.lower() in book["description"].lower()
        ]

    # 並び替え
    if sort == "rating":
        books.sort(
            key=lambda book: book["rating"],
            reverse=True
        )

    elif sort == "stock":
        books.sort(
            key=lambda book: book["stock"],
            reverse=True
        )

    context = {
        "books": books,
        "query": query,
        "sort": sort,
    }

    return render(
        request,
        "phone/book_search.html",
        context
    )


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