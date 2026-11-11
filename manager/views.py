from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.contrib import messages
from accounts.models import Department

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

import json
import re
import unicodedata
 
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
 
from library.models import Book, BookTag, Tag
from .models import Loan

# TODO: 実装が進んだら、管理者のみ許可する（@staff_member_required など）


PER_PAGE = 5


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
 
 
@login_required
@require_http_methods(["GET", "POST"])
def book_add(request):
    # 管理者のみ。他の manager ビューと同じ権限チェックに合わせて差し替えてください
    if getattr(request.user, "role", None) != "admin":
        raise PermissionDenied
 
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


def user_list(request):
    return render(request, "manager/user_list.html")


def user_detail(request, user_id):
    return render(request, "manager/user_detail.html", {"user_id": user_id})



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


def rental_list(request):
    order = request.GET.get("order", "desc")
    if order not in ("asc", "desc"):
        order = "desc"

    if order == "asc":
        ordering = ("loaned_on", "id")      # 古い順
    else:
        ordering = ("-loaned_on", "-id")    # 新着順

    loans = (
        Loan.objects.filter(returned_on__isnull=True)  # 貸出中のみ
        .select_related("student", "book")
        .order_by(*ordering)
    )
    paginator = Paginator(loans, 20)                   # 1ページ20件
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "manager/rental_list.html", {
        "page_obj": page_obj,
        "paginator": paginator,
        "loans": page_obj.object_list,
        "order": order,
    })



def rental_detail(request, rental_id):
    return render(request, "manager/rental_detail.html", {"rental_id": rental_id})


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