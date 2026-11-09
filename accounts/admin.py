from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, Student, TransactionQR, User


class StudentInline(admin.StackedInline):
    model = Student
    can_delete = False


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email",)
    inlines = [StudentInline]
    fieldsets = (
        (None, {"fields": ("email", "password", "role")}),
        ("権限", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("日時", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),
    )


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_no", "student_name", "department", "enrollment_year")
    search_fields = ("student_no", "student_name")


admin.site.register(Department)
admin.site.register(TransactionQR)