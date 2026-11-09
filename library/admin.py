from django.contrib import admin

from .models import (
    AdminNotice,
    Book,
    BookTag,
    Notice,
    NoticeClass,
    NoticeDate,
    Rental,
    Report,
    ReportClass,
    Review,
    ReviewTag,
    Tag,
)


class BookTagInline(admin.TabularInline):
    model = BookTag
    extra = 1


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "isbn", "total_copies", "is_suspended")
    list_filter = ("is_suspended",)
    search_fields = ("title", "author", "isbn")
    inlines = [BookTagInline]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    list_display = ("student", "book", "checkout_date", "due_date", "return_date", "is_lost")
    list_filter = ("is_lost",)
    search_fields = ("student__student_no", "student__student_name", "book__title", "book__isbn")
    date_hierarchy = "checkout_date"
    raw_id_fields = ("student", "book")


class ReviewTagInline(admin.TabularInline):
    model = ReviewTag
    extra = 0


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("book", "student", "point", "is_active", "created_at")
    list_filter = ("is_active", "point")
    search_fields = ("book__title", "student__student_name", "comment")
    raw_id_fields = ("student", "book")
    inlines = [ReviewTagInline]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("review", "student", "report_class", "reported_at", "is_seen")
    list_filter = ("is_seen", "report_class")
    raw_id_fields = ("student", "review")


class NoticeDateInline(admin.TabularInline):
    model = NoticeDate
    extra = 1


@admin.register(NoticeClass)
class NoticeClassAdmin(admin.ModelAdmin):
    list_display = ("name",)
    inlines = [NoticeDateInline]


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ("notice_class", "student", "rental", "sent_at", "is_success")
    list_filter = ("is_success", "notice_class")
    raw_id_fields = ("student", "rental")


@admin.register(AdminNotice)
class AdminNoticeAdmin(admin.ModelAdmin):
    list_display = ("notice_class", "student", "rental", "created_at", "is_seen")
    list_filter = ("is_seen", "notice_class")
    raw_id_fields = ("student", "rental")


admin.site.register(ReportClass)