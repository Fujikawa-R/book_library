from django.db import models
from django.utils import timezone

from accounts.models import Student

SOON_DAYS = 7  # 期限の何日前から「期限間近」にするか


class Book(models.Model):
    isbn = models.CharField("ISBN", max_length=13, unique=True)
    title = models.CharField("書名", max_length=200)

    def __str__(self):
        return self.title


class Loan(models.Model):
    """貸出記録。returned_on が空なら貸出中。"""
    student = models.ForeignKey(Student, verbose_name="借りた生徒", on_delete=models.PROTECT, related_name="loans")
    book = models.ForeignKey(Book, verbose_name="本", on_delete=models.PROTECT, related_name="loans")
    loaned_on = models.DateField("貸出日", default=timezone.localdate)
    due_on = models.DateField("返却期限")
    returned_on = models.DateField("返却日", null=True, blank=True)

    def __str__(self):
        return f"{self.book}({self.student})"

    @property
    def status(self):
        """overdue=期限切れ / soon=期限間近 / ok=期限前"""
        today = timezone.localdate()
        if self.due_on < today:
            return "overdue"
        if (self.due_on - today).days <= SOON_DAYS:
            return "soon"
        return "ok"