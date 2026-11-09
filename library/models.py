import calendar
from datetime import date

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


def add_months(base, months):
    """base の months か月後の日付を返す。月末は存在する日に丸める（例: 11/30 + 3か月 = 2/28）。"""
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# ---------------------------------------------------------------------------
# 図書
# ---------------------------------------------------------------------------

class Tag(models.Model):
    """タグ。図書と評価の両方に付ける。"""
    name = models.CharField("タグ名", max_length=50, unique=True)

    def __str__(self):
        return self.name


class Book(models.Model):
    """図書。ISBN単位で1件。貸出可能数は保存せず、貸出中の件数から計算する。"""
    title = models.CharField("タイトル", max_length=255)
    author = models.CharField("著者", max_length=255, blank=True)
    isbn = models.CharField("ISBN", max_length=13, unique=True)  # ハイフンなし13桁に正規化して保存する
    edition_year = models.PositiveSmallIntegerField("出版年", null=True, blank=True)
    total_copies = models.PositiveIntegerField("冊数", default=1)  # 紛失時は減らす
    is_suspended = models.BooleanField("貸出停止", default=False)
    created_at = models.DateTimeField("登録日時", default=timezone.now)

    tags = models.ManyToManyField(Tag, through="BookTag", related_name="books")

    def __str__(self):
        return self.title

    @property
    def lending_count(self):
        """貸出中の冊数。紛失扱いのものは数えない。"""
        return self.rentals.filter(return_date__isnull=True, is_lost=False).count()

    @property
    def available_copies(self):
        return self.total_copies - self.lending_count


class BookTag(models.Model):
    """図書とタグの中間テーブル。削除せず無効化する。"""
    book = models.ForeignKey(Book, verbose_name="図書", on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, verbose_name="タグ", on_delete=models.CASCADE)
    is_active = models.BooleanField("有効", default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["book", "tag"], name="unique_book_tag"),
        ]

    def __str__(self):
        return f"{self.book} - {self.tag}"


# ---------------------------------------------------------------------------
# 貸出
# ---------------------------------------------------------------------------

class Rental(models.Model):
    """貸出記録。return_date が NULL の間は貸出中。"""
    student = models.ForeignKey(
        "accounts.Student", verbose_name="生徒", on_delete=models.PROTECT, related_name="rentals"
    )
    book = models.ForeignKey(
        Book, verbose_name="図書", on_delete=models.PROTECT, related_name="rentals"
    )
    checkout_date = models.DateField("貸出日", default=timezone.localdate)
    due_date = models.DateField("返却期限", blank=True)  # 未指定なら save() で貸出日の3か月後を入れる
    return_date = models.DateField("返却日", null=True, blank=True)
    is_lost = models.BooleanField("紛失", default=False)

    class Meta:
        indexes = [
            models.Index(fields=["student", "return_date"], name="rental_student_return_idx"),
            models.Index(fields=["book", "return_date"], name="rental_book_return_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(return_date__isnull=True) | Q(return_date__gte=F("checkout_date")),
                name="rental_return_after_checkout",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.due_date is None:
            self.due_date = add_months(self.checkout_date, 3)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.book}（{self.checkout_date}）"

    @property
    def is_lending(self):
        """貸出中かどうか。"""
        return self.return_date is None and not self.is_lost

    @property
    def is_overdue(self):
        return self.is_lending and self.due_date < timezone.localdate()


# ---------------------------------------------------------------------------
# 評価・通報
# ---------------------------------------------------------------------------

class Review(models.Model):
    """図書の評価。1人1冊につき1件。削除せず無効化する。"""
    student = models.ForeignKey(
        "accounts.Student", verbose_name="生徒", on_delete=models.PROTECT, related_name="reviews"
    )
    book = models.ForeignKey(
        Book, verbose_name="図書", on_delete=models.PROTECT, related_name="reviews"
    )
    point = models.PositiveSmallIntegerField(
        "評価点", validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField("コメント", blank=True)
    created_at = models.DateTimeField("投稿日時", default=timezone.now)
    updated_at = models.DateTimeField("更新日時", auto_now=True)
    is_active = models.BooleanField("有効", default=True)  # ER図の is_deleted の逆

    tags = models.ManyToManyField(Tag, through="ReviewTag", related_name="reviews")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "book"], name="unique_review_per_student_book"),
            models.CheckConstraint(
                condition=Q(point__gte=1, point__lte=5),
                name="review_point_range",
            ),
        ]

    def __str__(self):
        return f"{self.book}：{self.point}点（{self.student}）"

    @property
    def is_deleted(self):
        return not self.is_active


class ReviewTag(models.Model):
    """評価とタグの中間テーブル。"""
    review = models.ForeignKey(Review, verbose_name="評価", on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, verbose_name="タグ", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["review", "tag"], name="unique_review_tag"),
        ]

    def __str__(self):
        return f"{self.review_id} - {self.tag}"


class ReportClass(models.Model):
    """通報の種別（マスタ）。"""
    name = models.CharField("通報種別", max_length=50)

    def __str__(self):
        return self.name


class Report(models.Model):
    """評価の通報。同じ生徒は同じ評価を1回だけ通報できる。"""
    student = models.ForeignKey(
        "accounts.Student", verbose_name="通報した生徒", on_delete=models.CASCADE, related_name="reports"
    )
    review = models.ForeignKey(
        Review, verbose_name="通報された評価", on_delete=models.CASCADE, related_name="reports"
    )
    report_class = models.ForeignKey(
        ReportClass, verbose_name="通報種別", on_delete=models.PROTECT, related_name="reports"
    )
    reported_at = models.DateTimeField("通報日時", default=timezone.now)
    comment = models.TextField("コメント", blank=True)
    is_seen = models.BooleanField("既読", default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "review"], name="unique_report_per_student_review"),
        ]

    def __str__(self):
        return f"{self.student} → 評価{self.review_id}（{self.report_class}）"


# ---------------------------------------------------------------------------
# 通知
# ---------------------------------------------------------------------------

class NoticeClass(models.Model):
    """通知の種別と通知文のテンプレート（マスタ）。"""
    name = models.CharField("通知種別", max_length=50)
    text = models.TextField("通知文")

    def __str__(self):
        return self.name


class NoticeDate(models.Model):
    """通知を送る日。interval_days が NULL なら1回のみ、あれば終了日まで間隔を空けて繰り返す。"""
    notice_class = models.ForeignKey(
        NoticeClass, verbose_name="通知種別", on_delete=models.CASCADE, related_name="dates"
    )
    notice_month = models.PositiveSmallIntegerField("開始月")
    notice_day = models.PositiveSmallIntegerField("開始日")
    interval_days = models.PositiveSmallIntegerField("繰り返し間隔（日）", null=True, blank=True)
    end_month = models.PositiveSmallIntegerField("終了月", null=True, blank=True)
    end_day = models.PositiveSmallIntegerField("終了日", null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(notice_month__gte=1, notice_month__lte=12),
                name="notice_date_month_range",
            ),
            models.CheckConstraint(
                condition=Q(notice_day__gte=1, notice_day__lte=31),
                name="notice_date_day_range",
            ),
            # 終了月と終了日は両方入れるか、両方空にする
            models.CheckConstraint(
                condition=(Q(end_month__isnull=True, end_day__isnull=True)
                           | Q(end_month__isnull=False, end_day__isnull=False)),
                name="notice_date_end_both_or_none",
            ),
            models.UniqueConstraint(
                fields=["notice_class", "notice_month", "notice_day"],
                name="unique_notice_date",
            ),
        ]

    def __str__(self):
        return f"{self.notice_class} {self.notice_month}/{self.notice_day}"


class Notice(models.Model):
    """生徒へのSlack通知の送信履歴。1行が1通。"""
    student = models.ForeignKey(
        "accounts.Student", verbose_name="宛先の生徒", on_delete=models.CASCADE, related_name="notices"
    )
    notice_class = models.ForeignKey(
        NoticeClass, verbose_name="通知種別", on_delete=models.PROTECT, related_name="notices"
    )
    rental = models.ForeignKey(
        Rental, verbose_name="対象の貸出", on_delete=models.CASCADE, related_name="notices"
    )
    sent_at = models.DateTimeField("送信日時", default=timezone.now)
    is_success = models.BooleanField("送信成功", default=True)  # Slack送信の成否

    def __str__(self):
        return f"{self.notice_class} → {self.student}"


class AdminNotice(models.Model):
    """管理者向けのアプリ内通知（Slackは使わない）。貸出・返却・4か月貸出中・卒業間近などで作られる。"""
    notice_class = models.ForeignKey(
        NoticeClass, verbose_name="通知種別", on_delete=models.PROTECT, related_name="admin_notices"
    )
    student = models.ForeignKey(
        "accounts.Student", verbose_name="対象の生徒", on_delete=models.CASCADE, related_name="admin_notices"
    )
    rental = models.ForeignKey(
        Rental, verbose_name="対象の貸出", on_delete=models.CASCADE, related_name="admin_notices"
    )
    created_at = models.DateTimeField("通知日時", default=timezone.now)
    is_seen = models.BooleanField("既読", default=False)  # 管理者全員で共通

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # 同じ貸出について、同じ種別の通知は1回だけ作る（二重通知の防止）
            models.UniqueConstraint(
                fields=["notice_class", "rental"], name="unique_admin_notice_per_rental"
            ),
        ]

    def __str__(self):
        return f"{self.notice_class}（{self.student}）"