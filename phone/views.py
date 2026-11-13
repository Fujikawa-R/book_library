import re
from django.http import Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q, Avg
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from library.models import Book, Rental, Review, Tag
from accounts.models import Student, Department, TransactionQR
from accounts.validators import normalize_school_email, normalize_student_email, email_enrollment_year_suffix

import qrcode
import qrcode.image.svg


# TODO: 実装が進んだら、ログイン必須（@login_required）と処理を追加する


def make_qr_svg(data):
    """文字列をQRコードのSVG文字列にする（テンプレートにそのまま埋め込む用）。"""
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return img.to_string(encoding="unicode")


@login_required
def mypage(request):
    student = get_object_or_404(Student.objects.select_related("user"), user=request.user)
    today = timezone.localdate()

    # 取引用QRは1日1つ。今日の分がなければ作る
    transaction_qr, _ = TransactionQR.objects.get_or_create(student=student, created_on=today)
    # TODO: QRに入れる中身は検討中。今は「日付:トークン」。
    #       トークンはDB上で生徒に紐づいているので、読み取り側は token で TransactionQR を引けば生徒を特定できる
    qr_data = f"{transaction_qr.created_on:%Y%m%d}:{transaction_qr.token}"

    rentals = student.rentals.select_related("book").order_by("-checkout_date")
    current_rentals = list(rentals.filter(return_date__isnull=True, is_lost=False))
    past_rentals = rentals.filter(return_date__isnull=False)

    # 返却期限までの残り日数（マイナスなら延滞）
    for rental in current_rentals:
        rental.days_left = (rental.due_date - today).days
        rental.overdue_days = -rental.days_left
        # カードの色分け: 期限切れ・当日=赤、2週間以内=黄、それ以外=primary(青)
        if rental.days_left <= 0:
            rental.level = "is-danger"
        elif rental.days_left <= 14:
            rental.level = "is-warning"
        else:
            rental.level = ""

    return render(request, "phone/mypage.html", {
        "student": student,
        "qr_svg": make_qr_svg(qr_data),
        "current_rentals": current_rentals,
        "past_rentals": past_rentals,
    })

def check_student_name(name):
    """名前の入力チェック。問題があればエラーメッセージ、なければ None。"""
    if not name:
        return "名前を入力してください。"
    if len(name) > Student._meta.get_field("student_name").max_length:
        return "名前は50文字以内で入力してください。"
    return None


@login_required
def setting(request):
    # 生徒は Student を持つ。管理者は持たないので、メールとパスワードだけ変更できる
    student = Student.objects.select_related("user", "department").filter(user=request.user).first()
    is_admin = request.user.role == User.Role.ADMIN or request.user.is_superuser
    if student is None and not is_admin:
        raise Http404("この画面は生徒・管理者のみ利用できます。")

    departments = Department.objects.filter(is_active=True)

    error = None
    success = {
        "1": "設定を保存しました。",
        "password": "パスワードを変更しました。",
    }.get(request.GET.get("saved"))

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        student_name = request.POST.get("student_name", "").strip()
        department_id = request.POST.get("department", "")

        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        department = Department.objects.filter(
            id=department_id,
            is_active=True
        ).first() if department_id.isdigit() else None

        # メールアドレスを変更したときだけ形式をチェックする
        # （チェック導入前に登録したアカウントでも、名前やパスワードは変更できるように）
        email_changed = email != request.user.email.lower()
        email_error = None
        if email_changed and student is None:
            # 管理者：学校ドメインかどうかだけチェック
            try:
                email = normalize_school_email(email)
            except ValidationError as e:
                email_error = e.messages[0]
        elif email_changed:
            try:
                email = normalize_student_email(email)
            except ValidationError as e:
                email_error = e.messages[0]
            else:
                if email_enrollment_year_suffix(email) != str(student.enrollment_year)[-2:]:
                    email_error = "メールアドレスの入学年が登録済みの入学年と一致しません。"

        # 名前・学科は生徒のときだけ
        name_error = check_student_name(student_name) if student else None

        if name_error:
            error = name_error

        elif email_error:
            error = email_error

        elif User.objects.filter(email__iexact=email).exclude(
            pk=request.user.pk
        ).exists():
            error = "このメールアドレスは既に使用されています。"

        elif student is not None and department is None:
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

                    if student is not None:
                        student.student_name = student_name
                        student.department = department
                        student.save(update_fields=["student_name", "department"])

                if new_password:
                    update_session_auth_hash(request, request.user)

                saved = "password" if new_password else "1"
                return redirect(f"{reverse('phone:setting')}?saved={saved}")

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

REVIEW_TAG_LIMIT = 5  # 1件の口コミに付けられるタグの上限
TAG_NAME_MAX_LENGTH = Tag._meta.get_field("name").max_length


@login_required
def book_detail(request, isbn):
    """図書詳細。自分の口コミの投稿・編集・削除もこの画面で行う（POST）。"""
    book = get_object_or_404(
        Book,
        isbn=isbn,
        is_suspended=False
    )

    # 生徒は生徒として、管理者は無条件で口コミを書ける。それ以外（貸借PCなど）は閲覧のみ
    student = Student.objects.filter(user=request.user).first()
    is_admin = request.user.role == User.Role.ADMIN or request.user.is_superuser

    if student is not None:
        author = {"student": student}
    elif is_admin:
        author = {"admin_user": request.user}
    else:
        author = None

    # 削除済み（無効化）を含めて自分の口コミを取得する（1人1冊1件の制約があるため）
    my_review = None
    if author is not None:
        my_review = Review.objects.filter(book=book, **author).first()

    error = None
    form_point = my_review.point if my_review and my_review.is_active else ""
    form_comment = my_review.comment if my_review and my_review.is_active else ""
    form_tag_ids = (
        [str(pk) for pk in my_review.tags.values_list("pk", flat=True)]
        if my_review and my_review.is_active else []
    )
    form_new_tags = ""

    if request.method == "POST":
        if author is None:
            error = "このアカウントでは口コミを投稿できません。"

        elif request.POST.get("action") == "delete":
            if my_review is not None and my_review.is_active:
                my_review.is_active = False
                my_review.save(update_fields=["is_active", "updated_at"])
            return redirect("phone:book_detail", isbn=book.isbn)

        else:
            point = request.POST.get("point", "")
            comment = request.POST.get("comment", "").strip()
            form_point, form_comment = point, comment

            # タグ：既存タグはチェックボックス、新しいタグは「,」「、」や空白区切りで入力
            form_tag_ids = [t for t in request.POST.getlist("tags") if t.isdigit()]
            form_new_tags = request.POST.get("new_tags", "").strip()
            selected_tags = list(Tag.objects.filter(pk__in=form_tag_ids))
            new_tag_names = list(dict.fromkeys(
                name for name in re.split(r"[,、，\s]+", form_new_tags) if name
            ))
            tag_count = len({t.name for t in selected_tags} | set(new_tag_names))

            if not point.isdigit() or not 1 <= int(point) <= 5:
                error = "評価点を1〜5で選択してください。"
            elif len(comment) > 1000:
                error = "コメントは1000文字以内で入力してください。"
            elif any(len(name) > TAG_NAME_MAX_LENGTH for name in new_tag_names):
                error = f"タグは1つ{TAG_NAME_MAX_LENGTH}文字以内で入力してください。"
            elif tag_count > REVIEW_TAG_LIMIT:
                error = f"タグは{REVIEW_TAG_LIMIT}個まで付けられます。"
            else:
                with transaction.atomic():
                    if my_review is None:
                        my_review = Review(book=book, **author)
                    my_review.point = int(point)
                    my_review.comment = comment
                    my_review.is_active = True
                    my_review.save()

                    for name in new_tag_names:
                        tag, _ = Tag.objects.get_or_create(name=name)
                        selected_tags.append(tag)
                    my_review.tags.set(selected_tags)
                return redirect("phone:book_detail", isbn=book.isbn)

    reviews = Review.objects.filter(
        book=book,
        is_active=True
    ).select_related("student__department").prefetch_related("tags").order_by("-updated_at")

    book.rating = reviews.aggregate(
        average=Avg("point")
    )["average"]

    # 自分の口コミは「その他の口コミ」に出さない
    other_reviews = reviews.exclude(**author) if author else reviews

    rental_count = Rental.objects.filter(
        book=book,
        return_date__isnull=True,
        is_lost=False
    ).count()

    book.stock = max(0, book.total_copies - rental_count)

    return render(request, 'phone/book_detail.html', {
        'book': book,
        'can_review': author is not None,
        'can_report': student is not None,  # 通報は生徒のみ（Report.student が必須のため）
        'my_review': my_review if my_review and my_review.is_active else None,
        'reviews': other_reviews,
        'error': error,
        'form_point': str(form_point),
        'form_comment': form_comment,
        'point_choices': ["5", "4", "3", "2", "1"],
        'tag_choices': Tag.objects.order_by("name"),
        'form_tag_ids': form_tag_ids,
        'form_new_tags': form_new_tags,
        'review_tag_limit': REVIEW_TAG_LIMIT,
    })

def signup(request):
    if request.user.is_authenticated:
        return redirect("phone:login")

    errors = []
    email = ""
    student_id = ""
    student_name = ""
    selected_department = ""
    admission_year = ""

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        student_id = request.POST.get("student_id", "").strip()
        student_name = request.POST.get("student_name", "").strip()
        selected_department = request.POST.get("department", "")
        admission_year = request.POST.get("admission_year", "").strip()
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        # メールアドレスの形式・ドメイン確認
        email_ok = False
        try:
            email = normalize_student_email(email)
            email_ok = True
        except ValidationError as e:
            errors.extend(e.messages)

        # メールアドレスの重複確認
        if email_ok and User.objects.filter(email__iexact=email).exists():
            errors.append("このメールアドレスは既に登録されています。")

        # 学籍番号の重複確認
        if Student.objects.filter(student_no = student_id).exists():
            errors.append("この学籍番号は既に登録されています。")

        # パスワード確認
        if password1 != password2:
            errors.append("パスワードが一致しません")

        # 学科の確認
        department = Department.objects.filter(
            id = selected_department,
            is_active = True
        ).first() if selected_department.isdigit() else None

        if department is None:
            errors.append("学科を選択してください")
       
        #入学年の確認
        try:
            year = int(admission_year)
            if not 2000 <= year <= timezone.localdate().year:
                errors.append("入学年を正しく入力してください。")
        except ValueError:
            year = None
            errors.append("入学年を入力して下さい。")

        # メールアドレスと入学年の一致確認
        if year is not None and email_ok:
            if email_enrollment_year_suffix(email) != str(year)[-2:]:
                errors.append(
                    "メールアドレスの入学年と入力された入学年が一致しません"
                )

        if not student_id:
            errors.append("学籍番号を入力してください。")

        # 名前の確認
        name_error = check_student_name(student_name)
        if name_error:
            errors.append(name_error)

        #登録
        if not errors:
            with transaction.atomic():
                user = User.objects.create_user(
                    email = email,
                    password=password1,
                    role = User.Role.STUDENT
                )

                Student.objects.create(
                    user = user,
                    student_no = student_id,
                    student_name = student_name,
                    department = department,
                    enrollment_year = year
                )

            login(request,user)
            return redirect("phone:mypage")

    departments = Department.objects.filter(
        is_active=True
    ).order_by("name")
    return render(request, "phone/signup.html",{
        "errors":errors,
        "email": email,
        "student_id": student_id,
        "student_name": student_name,
        "selected_department": selected_department,
        "admission_year": admission_year,
        "departments": departments,
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
