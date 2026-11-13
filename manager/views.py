from datetime import timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib import messages
from accounts.models import Department, Student

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

import json
import re
import unicodedata
 
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
 
from library.models import Book, BookTag, Tag
from .decorators import admin_required
from .models import Loan

# このファイルのビューはすべて管理者専用（@admin_required）


PER_PAGE = 5


@admin_required
def book_list(request):
    keyword = request.GET.get("q", "").strip()
    order = request.GET.get("order", "new")  # new: 新着順 / old: 古い順

    # 貸出中の冊数（紛失扱いは除く）をまとめて数える。Book.available_copies を
    # 1冊ずつ呼ぶと一覧の件数分クエリが増えるので、ここで一括集計する。
    books = Book.objects.annotate(
        lending=Count(
            "rentals",
            filter=Q(rentals__return_date__isnull=True, rentals__is_lost=False),
        )
    ).annotate(available=F("total_copies") - F("lending"))

    if keyword:
        books = books.filter(
            Q(title__icontains=keyword)
            | Q(author__icontains=keyword)
            | Q(isbn__icontains=keyword)
        )

    if order == "old":
        books = books.order_by("created_at", "id")
    else:
        order = "new"
        books = books.order_by("-created_at", "-id")

    page_obj = Paginator(books, PER_PAGE).get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "keyword": keyword,
        "order": order,
        # ページ送りのリンク用（検索語と並び順を引き継ぐ）
        "base_query": urlencode({"q": keyword, "order": order}),
        # 並び替えボタン用（並び順だけ反転）
        "sort_query": urlencode(
            {"q": keyword, "order": "old" if order == "new" else "new"}
        ),
    }
    return render(request, "manager/book_list.html", context)


MAX_QTY = 999
 
 
def _normalize_isbn(raw):
    """全角数字をNFKCで半角にし、ハイフンと空白を除く。"""
    return re.sub(r"[-\s]", "", unicodedata.normalize("NFKC", str(raw)))
 
 
def _is_valid_isbn13(isbn):
    """978/979始まりの13桁で、チェックディジットが合っているか。"""
    if not re.fullmatch(r"97[89]\d{10}", isbn):
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn[:12]))
    return (10 - total % 10) % 10 == int(isbn[12])
 
 
def _parse_books(raw_json):
    """POSTされたJSONを検証して (items, errors) を返す。同じISBNは冊数を合算する。"""
    try:
        data = json.loads(raw_json or "")
    except ValueError:
        return [], ["送信データを読み取れませんでした。"]
    if not isinstance(data, list) or not data:
        return [], ["登録する本がありません。"]
 
    title_max = Book._meta.get_field("title").max_length
    author_max = Book._meta.get_field("author").max_length
 
    merged = {}
    errors = []
    for n, row in enumerate(data, start=1):
        label = f"{n}件目"
        if not isinstance(row, dict):
            errors.append(f"{label}: データの形式が正しくありません。")
            continue
 
        isbn = _normalize_isbn(row.get("isbn", ""))
        title = str(row.get("title", "")).strip()
        author = str(row.get("author", "")).strip()
        try:
            qty = int(row.get("qty", 1))
        except (TypeError, ValueError):
            qty = 0
 
        if not _is_valid_isbn13(isbn):
            errors.append(f"{label}: ISBNが正しくありません（{isbn or '空'}）。")
            continue
        if not title:
            errors.append(f"{label}（{isbn}）: タイトルを入力してください。")
            continue
        if title_max and len(title) > title_max:
            errors.append(f"{label}（{isbn}）: タイトルは{title_max}文字以内にしてください。")
            continue
        if author_max and len(author) > author_max:
            errors.append(f"{label}（{isbn}）: 著者は{author_max}文字以内にしてください。")
            continue
        if not 1 <= qty <= MAX_QTY:
            errors.append(f"{label}（{isbn}）: 冊数は1〜{MAX_QTY}の整数にしてください。")
            continue
 
        if isbn in merged:
            merged[isbn]["qty"] += qty
        else:
            merged[isbn] = {"isbn": isbn, "title": title, "author": author, "qty": qty}
 
    return list(merged.values()), errors
 
 
@admin_required
@require_http_methods(["GET", "POST"])
def book_add(request):
    if request.method == "GET":
        return render(request, "manager/book_add.html")
 
    items, errors = _parse_books(request.POST.get("books"))
    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, "manager/book_add.html", status=400)
 
    created = 0
    increased = 0
    total_copies = 0
    with transaction.atomic():
        for item in items:
            # 既存ならタイトル・著者は変えず、冊数だけ加算する
            updated = Book.objects.filter(isbn=item["isbn"]).update(
                total_copies=F("total_copies") + item["qty"]
            )
            if updated:
                increased += 1
            else:
                Book.objects.create(
                    isbn=item["isbn"],
                    title=item["title"],
                    author=item["author"],
                    total_copies=item["qty"],
                )
                created += 1
            total_copies += item["qty"]
 
    parts = []
    if created:
        parts.append(f"{created}種類を新規登録")
    if increased:
        parts.append(f"{increased}種類の冊数を追加")
    messages.success(request, f"{'、'.join(parts)}しました（合計{total_copies}冊）。")
    return redirect("manager:book_list")


def _get_tags(book):
    """この図書に付いているタグを名前順で返す。"""
    tag_ids = BookTag.objects.filter(book=book, is_active=True).values("tag_id")
    return Tag.objects.filter(pk__in=tag_ids).order_by("name")
 
 
def _attach_tag(book, name):
    """名前からタグを取得（なければ作成）して図書に付ける。"""
    name = name.strip()
    if not name:
        return
    tag, _ = Tag.objects.get_or_create(name=name)
    booktag, created = BookTag.objects.get_or_create(book=book, tag=tag)
    if not created and not booktag.is_active:
        booktag.is_active = True
        booktag.save(update_fields=["is_active"])
 
 
def _rename_tags(book, tag_ids, post):
    """この図書のタグだけを新しい名前に付け替える（他の図書のタグ名は変えない）。"""
    for tag_id in tag_ids:
        new_name = post.get(f"new_name_{tag_id}", "").strip()
        if not new_name:
            continue
        old = BookTag.objects.filter(
            book=book, tag_id=tag_id, is_active=True
        ).select_related("tag").first()
        if old is None or old.tag.name == new_name:
            continue
        old.is_active = False
        old.save(update_fields=["is_active"])
        _attach_tag(book, new_name)
 
 
def _detach_tags(book, tag_ids):
    """この図書からタグを外す（タグ自体や他の図書の紐づけは残す）。"""
    BookTag.objects.filter(book=book, tag_id__in=tag_ids).update(is_active=False)
 
 
@admin_required
def book_detail(request, isbn):
    book = get_object_or_404(Book, isbn=isbn)
 
    if request.method == "POST":
        action = request.POST.get("action", "")
        selected = request.POST.getlist("selected_tags")
 
        with transaction.atomic():
            if action == "save":
                title = request.POST.get("title", "").strip()
                author = request.POST.get("author", "").strip()
                if title:
                    book.title = title
                if author:
                    book.author = author
                try:
                    copies = int(request.POST.get("total_copies", ""))
                except ValueError:
                    copies = None
                if copies is not None and copies >= 0:
                    book.total_copies = copies
                book.save(update_fields=["title", "author", "total_copies"])
 
                # 既存タグの名前変更と、「タグを追加」で作った空行の新規タグ
                current_ids = [t.pk for t in _get_tags(book)]
                _rename_tags(book, current_ids, request.POST)
                for name in request.POST.getlist("add_tag_name"):
                    _attach_tag(book, name)
 
                # 保存したら図書一覧へ戻る
                return redirect("manager:book_list")
 
            elif action == "bulk_edit":
                _rename_tags(book, selected, request.POST)
 
            elif action == "bulk_delete":
                _detach_tags(book, selected)
 
            elif action == "suspend_book":
                # データは残して貸出だけ停止する
                book.is_suspended = True
                book.save(update_fields=["is_suspended"])
                return redirect("manager:book_list")
 
            elif action == "resume_book":
                book.is_suspended = False
                book.save(update_fields=["is_suspended"])
                return redirect("manager:book_list")
 
            elif "edit_tag" in request.POST:
                _rename_tags(book, [request.POST["edit_tag"]], request.POST)
 
            elif "delete_tag" in request.POST:
                _detach_tags(book, [request.POST["delete_tag"]])
 
        return redirect("manager:book_detail", isbn=book.isbn)
 
    return render(
        request,
        "manager/book_detail.html",
        {"book": book, "tags": _get_tags(book)},
    )


USER_PER_PAGE = 20


def _school_year(today=None):
    """今日が属する年度（4月始まり）。Student.grade と同じ計算。"""
    today = today or timezone.localdate()
    return today.year if today.month >= 4 else today.year - 1


def _int_param(request, name):
    """数字ならその文字列を、それ以外は空文字を返す（テンプレートの selected 判定用に文字列のまま）。"""
    value = request.GET.get(name, "").strip()
    return value if value.isdigit() else ""


@admin_required
def user_list(request):
    # mode: "" = 通常（有効なユーザー） / "inactive" = 無効化されたユーザー
    mode = "inactive" if request.GET.get("mode") == "inactive" else ""
    keyword = request.GET.get("q", "").strip()
    order = "asc" if request.GET.get("order") == "asc" else "desc"
    department = _int_param(request, "department")
    grade = _int_param(request, "grade") if not mode else ""
    enrollment_year = _int_param(request, "enrollment_year") if mode else ""

    school_year = _school_year()

    # モードごとの母集団。絞り込みの選択肢はここから作る
    base = Student.objects.filter(user__is_active=(mode != "inactive"))

    students = base.select_related("department", "user")

    if keyword:
        students = students.filter(
            Q(student_name__icontains=keyword) | Q(student_no__icontains=keyword)
        )
    if department:
        students = students.filter(department_id=department)
    if grade:
        # 学年は保存していないので入学年に変換して絞り込む
        students = students.filter(enrollment_year=school_year - int(grade) + 1)
    if enrollment_year:
        students = students.filter(enrollment_year=enrollment_year)

    students = students.order_by("student_no" if order == "asc" else "-student_no")

    page_obj = Paginator(students, USER_PER_PAGE).get_page(request.GET.get("page"))

    # 選択肢：今のモードに実際にいる生徒の学科・入学年だけを出す
    # （無効ユーザーは削除済みの学科に属していることもあるので is_active では絞らない）
    departments = Department.objects.filter(student__in=base).distinct().order_by("id")
    years = sorted(set(base.values_list("enrollment_year", flat=True)), reverse=True)
    grades = sorted({school_year - y + 1 for y in years if school_year - y + 1 >= 1})

    # ページ送り・並び替えで条件を引き継ぐためのクエリ（空の値は省く）
    params = {
        "mode": mode,
        "q": keyword,
        "department": department,
        "grade": grade,
        "enrollment_year": enrollment_year,
    }
    params = {k: v for k, v in params.items() if v}

    context = {
        "page_obj": page_obj,
        "mode": mode,
        "keyword": keyword,
        "order": order,
        "department": department,
        "grade": grade,
        "enrollment_year": enrollment_year,
        "departments": departments,
        "grades": grades,
        "enrollment_years": years,
        "base_query": urlencode({**params, "order": order}),
        "sort_query": urlencode({**params, "order": "desc" if order == "asc" else "asc"}),
    }
    return render(request, "manager/user_list.html", context)


@admin_required
def user_detail(request, user_id):
    student = get_object_or_404(
        Student.objects.select_related("department", "user"), user_id=user_id
    )
    rentals = student.rentals.select_related("book").order_by("-checkout_date", "-id")
    return render(request, "manager/user_detail.html", {
        "student": student,
        "rentals": rentals,
    })



DEPT_YEARS_MIN = 1
DEPT_YEARS_MAX = 6
# 在籍中の生徒＝アカウントが有効な生徒
ACTIVE_STUDENTS = Count("student", filter=Q(student__user__is_active=True))


def _parse_years(raw):
    try:
        years = int(raw)
    except (TypeError, ValueError):
        return None
    return years if DEPT_YEARS_MIN <= years <= DEPT_YEARS_MAX else None


def _save_departments(post):
    """学科の更新・削除・追加をまとめて検証する。
    エラーがなければ保存して (エラーなし, 復元した学科名) を、あれば (エラー, []) を返す。"""
    errors = []
    name_max = Department._meta.get_field("name").max_length
    delete_ids = set(post.getlist("delete_ids"))

    def check_name(name, label):
        if not name:
            errors.append(f"{label}: 学科名を入力してください。")
        elif len(name) > name_max:
            errors.append(f"{label}: 学科名は{name_max}文字以内にしてください。")

    def years_error(label):
        errors.append(f"{label}: 年数は{DEPT_YEARS_MIN}〜{DEPT_YEARS_MAX}の数字にしてください。")

    # 既存の学科
    submitted = {
        str(d.pk): d
        for d in Department.objects.filter(
            pk__in=post.getlist("department_ids"), is_active=True
        ).annotate(active_students=ACTIVE_STUDENTS)
    }
    to_delete, to_update = [], []
    for dept_id, dept in submitted.items():
        if dept_id in delete_ids:
            if dept.active_students:
                errors.append(
                    f"「{dept.name}」には在籍中の生徒が{dept.active_students}人いるため削除できません。"
                )
            to_delete.append(dept)
            continue
        name = post.get(f"name_{dept_id}", dept.name).strip()
        years = _parse_years(post.get(f"course_years_{dept_id}", dept.course_years))
        check_name(name, f"「{dept.name}」")
        if years is None:
            years_error(f"「{dept.name}」")
        to_update.append((dept, name, years))

    # 新しい学科（学科名も年数も空の行は無視する）
    to_create = []
    for n, (name, raw_years) in enumerate(
        zip(post.getlist("new_name"), post.getlist("new_course_years")), start=1
    ):
        name = name.strip()
        if not name and not raw_years:
            continue
        label = f"追加{n}行目"
        years = _parse_years(raw_years)
        check_name(name, label)
        if years is None:
            years_error(label)
        to_create.append((name, years))

    # 学科名の重複チェック
    kept_names = [name for _, name, _ in to_update] + [name for name, _ in to_create]
    for name in {n for n in kept_names if kept_names.count(n) > 1}:
        errors.append(f"「{name}」が複数あります。学科名は重複できません。")
    others = Department.objects.filter(name__in=kept_names).exclude(
        pk__in=[d.pk for d in to_delete] + [d.pk for d, _, _ in to_update]
    )
    inactive = {d.name: d for d in others if not d.is_active}
    for d in others:
        if d.is_active:
            errors.append(f"「{d.name}」はすでに登録されています。")
    for dept, name, _ in to_update:
        if name != dept.name and name in inactive:
            errors.append(
                f"「{name}」は削除済みの学科です。名前を変えずに「学科を追加」から追加すると復元できます。"
            )

    if errors:
        return errors, []

    restored = []
    with transaction.atomic():
        for dept in to_delete:
            dept.is_active = False   # 論理削除
            dept.save(update_fields=["is_active"])
        for dept, name, years in to_update:
            dept.name, dept.course_years = name, years
            dept.save(update_fields=["name", "course_years"])
        for name, years in to_create:
            old = inactive.get(name)
            if old:
                # 削除済みの同名学科があれば、新しく作らずに復元する（生徒との紐づけも戻る）
                old.is_active, old.course_years = True, years
                old.save(update_fields=["is_active", "course_years"])
                restored.append(name)
            else:
                Department.objects.create(name=name, course_years=years)
    return [], restored


@admin_required
def department_list(request):
    if request.method == "POST":
        try:
            errors, restored = _save_departments(request.POST)
        except IntegrityError:
            # 学科名の入れ替えなどで一時的に重複した場合
            errors, restored = ["学科名が重複したため保存できませんでした。"], []
        if errors:
            for e in errors:
                messages.error(request, e)
            messages.error(request, "変更は保存されていません。")
        else:
            messages.success(request, "学科を保存しました。")
            for name in restored:
                messages.info(request, f"削除済みだった「{name}」を復元しました。")
        return redirect("manager:department_list")

    departments = (
        Department.objects.filter(is_active=True)
        .annotate(active_students=ACTIVE_STUDENTS)
        .order_by("id")
    )
    return render(request, "manager/department_list.html", {"departments": departments})


SOON_DAYS = 3  # 返却日まで何日以内を「期限間近」とするか（運用に合わせて変更）
LOAN_STATUSES = ("overdue", "soon", "ok")


@admin_required
def rental_list(request):
    order = request.GET.get("order", "desc")
    if order not in ("asc", "desc"):
        order = "desc"

    status = request.GET.get("status", "")
    if status not in LOAN_STATUSES:
        status = ""  # 想定外の値は「すべて」に戻す

    if order == "asc":
        ordering = ("loaned_on", "id")      # 古い順
    else:
        ordering = ("-loaned_on", "-id")    # 新着順

    today = timezone.localdate()
    soon_limit = today + timedelta(days=SOON_DAYS)

    loans = (
        Loan.objects.filter(returned_on__isnull=True)  # 貸出中のみ
        .select_related("student", "book")
    )

    # 状態での絞り込み（アイコンの判定と同じ条件）
    if status == "overdue":
        loans = loans.filter(due_on__lt=today)
    elif status == "soon":
        loans = loans.filter(due_on__gte=today, due_on__lte=soon_limit)
    elif status == "ok":
        loans = loans.filter(due_on__gt=soon_limit)

    loans = loans.order_by(*ordering)

    paginator = Paginator(loans, 20)                   # 1ページ20件
    page_obj = paginator.get_page(request.GET.get("page"))

    # loan.status は Loan モデルのプロパティをそのまま使う（ここでは代入しない）
    return render(request, "manager/rental_list.html", {
        "page_obj": page_obj,
        "paginator": paginator,
        "loans": page_obj.object_list,
        "order": order,
        "status": status,
    })



@admin_required
def rental_detail(request, rental_id):
    return render(request, "manager/rental_detail.html", {"rental_id": rental_id})


@admin_required
def report_list(request):
    return render(request, "manager/report_list.html")


@admin_required
def report_detail(request, report_id):
    return render(request, "manager/report_detail.html", {"report_id": report_id})


@admin_required
def notice_list(request):
    return render(request, "manager/notice_list.html")


@admin_required
def user_notice_list(request):
    return render(request, "manager/user_notice_list.html")


@admin_required
def user_notice_text_list(request):
    return render(request, "manager/user_notice_text_list.html")


@admin_required
@require_POST
def book_suspend_toggle(request, isbn):
    # TODO: 貸出停止・解除
    return redirect("manager:book_detail", isbn=isbn)


@admin_required
@require_POST
def book_lost(request, isbn):
    # TODO: 紛失処理（冊数を減らす）
    return redirect("manager:book_detail", isbn=isbn)


@admin_required
@require_POST
def user_deactivate(request, user_id):
    """手動の無効化。User.is_active を False にする（論理削除）。"""
    student = get_object_or_404(Student.objects.select_related("user"), user_id=user_id)
    user = student.user

    if not user.is_active:
        messages.info(request, f"{student.student_name} さんはすでに無効化されています。")
        return redirect("manager:user_detail", user_id=user_id)

    user.is_active = False
    user.save(update_fields=["is_active"])

    lending = student.rentals.filter(return_date__isnull=True, is_lost=False).count()
    if lending:
        messages.warning(
            request,
            f"{student.student_name} さんを無効化しました。未返却の本が {lending} 冊あります。",
        )
    else:
        messages.success(request, f"{student.student_name} さんを無効化しました。")
    return redirect("manager:user_detail", user_id=user_id)


@admin_required
@require_POST
def user_extend_graduation(request, user_id):
    """留年。卒業年の延長を1年増やす（無効化されるのも1年後ろにずれる）。"""
    student = get_object_or_404(
        Student.objects.select_related("user", "department"), user_id=user_id
    )

    if not student.user.is_active:
        messages.error(request, "無効化されたユーザーは留年させられません。")
        return redirect("manager:user_detail", user_id=user_id)

    # 同時に押されても取りこぼさないよう DB 側で加算する
    Student.objects.filter(pk=student.pk).update(
        graduation_extension=F("graduation_extension") + 1
    )
    student.refresh_from_db(fields=["graduation_extension"])

    messages.success(
        request,
        f"{student.student_name} さんを留年にしました。"
        f"卒業日は {student.graduation_date:%Y/%m/%d} になります。",
    )
    return redirect("manager:user_detail", user_id=user_id)


@admin_required
@require_POST
def user_cancel_extension(request, user_id):
    """留年取消。卒業年の延長を1年減らす（0未満にはしない）。"""
    student = get_object_or_404(
        Student.objects.select_related("user", "department"), user_id=user_id
    )

    if not student.user.is_active:
        messages.error(request, "無効化されたユーザーの留年は取り消せません。")
        return redirect("manager:user_detail", user_id=user_id)

    if student.graduation_extension <= 0:
        messages.error(request, f"{student.student_name} さんは留年していません。")
        return redirect("manager:user_detail", user_id=user_id)

    # 取り消すと卒業日が過ぎてしまう場合は止める（翌日に無効化されるべき状態になるため）
    new_graduation = student.graduation_date.replace(year=student.graduation_date.year - 1)
    if new_graduation < timezone.localdate():
        messages.error(
            request,
            f"取り消すと卒業日（{new_graduation:%Y/%m/%d}）が過ぎてしまうため取り消せません。",
        )
        return redirect("manager:user_detail", user_id=user_id)

    # 0未満にならないよう条件付きで DB 側で減算する
    updated = Student.objects.filter(pk=student.pk, graduation_extension__gt=0).update(
        graduation_extension=F("graduation_extension") - 1
    )
    if not updated:
        messages.error(request, f"{student.student_name} さんは留年していません。")
        return redirect("manager:user_detail", user_id=user_id)

    student.refresh_from_db(fields=["graduation_extension"])
    messages.success(
        request,
        f"{student.student_name} さんの留年を取り消しました。"
        f"卒業日は {student.graduation_date:%Y/%m/%d} になります。",
    )
    return redirect("manager:user_detail", user_id=user_id)


@admin_required
@require_POST
def department_deactivate(request, department_id):
    # TODO: 学科の無効化（アクティブな生徒がいないときのみ）
    return redirect("manager:department_list")


@admin_required
@require_POST
def report_delete_review(request, report_id):
    # TODO: 通報された評価の削除
    return redirect("manager:report_detail", report_id=report_id)