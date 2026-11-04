import secrets
from datetime import date

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class Department(models.Model):
    name = models.CharField("学科名", max_length=50, unique=True)
    course_years = models.PositiveSmallIntegerField("修業年限", default=3)
    is_active = models.BooleanField("有効", default=True)  # 削除せず無効化する

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("メールアドレスは必須です")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)

    def create_lender(self, number, password=None):
        """貸借PC用アカウント。メールアドレスを持たないので内部用の識別子を入れる。"""
        email = f"lender{number}@lender.invalid"  # .invalid は実在しない予約ドメイン
        return self.create_user(email, password, role=User.Role.LENDER)


class User(AbstractBaseUser, PermissionsMixin):
    """認証用。管理者・貸借PC・生徒の3種類をroleで区別する。"""

    class Role(models.TextChoices):
        ADMIN = "admin", "管理者"
        LENDER = "lender", "貸借PC"
        STUDENT = "student", "生徒"

    email = models.EmailField("メールアドレス", unique=True)  # ER図の mail
    role = models.CharField("種別", max_length=10, choices=Role.choices, default=Role.STUDENT)
    is_active = models.BooleanField("有効", default=True)  # ER図の is_deleted の逆
    is_staff = models.BooleanField("管理画面に入れる", default=False)
    created_at = models.DateTimeField("作成日時", default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def is_deleted(self):
        return not self.is_active


class Student(models.Model):
    """生徒の情報。Userと1対1。"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student")
    student_no = models.CharField("学籍番号", max_length=20, unique=True)
    student_name = models.CharField("氏名", max_length=50)
    slack_id = models.CharField("Slack ID", max_length=20, unique=True, null=True, blank=True)
    department = models.ForeignKey(Department, verbose_name="学科", on_delete=models.PROTECT)
    enrollment_year = models.PositiveSmallIntegerField("入学年")
    graduation_extension = models.PositiveSmallIntegerField("卒業年の延長（年）", default=0)

    def __str__(self):
        return f"{self.student_name}（{self.student_no}）"

    @property
    def graduation_date(self):
        """入学年 + 修業年限 + 延長 の年の3月31日。アカウント無効化はその翌日（4/1）。"""
        year = self.enrollment_year + self.department.course_years + self.graduation_extension
        return date(year, 3, 31)

    @property
    def grade(self):
        """学年。年度（4月始まり）から計算するので保存しない。"""
        today = timezone.localdate()
        school_year = today.year if today.month >= 4 else today.year - 1
        return school_year - self.enrollment_year + 1

    @property
    def is_deleted(self):
        return self.user.is_deleted


def generate_token():
    return secrets.token_urlsafe(32)


class TransactionQR(models.Model):
    """貸借PCでの取引（貸出・返却）認証用QR。1日ごとに生成する。"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="transaction_qrs")
    token = models.CharField(max_length=64, unique=True, default=generate_token)
    created_on = models.DateField(default=timezone.localdate)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "created_on"], name="unique_qr_per_student_per_day"),
        ]

    def is_valid(self):
        return self.created_on == timezone.localdate()  # 有効期限は1日