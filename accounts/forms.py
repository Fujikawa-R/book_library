from datetime import date

from django import forms
from django.conf import settings
from django.contrib.auth.forms import BaseUserCreationForm
from django.db import transaction

from .models import Department, Student, User


class SignUpForm(BaseUserCreationForm):
    student_no = forms.CharField(label="学籍番号", max_length=20)
    student_name = forms.CharField(label="氏名", max_length=50)
    department = forms.ModelChoiceField(label="学科", queryset=Department.objects.none())
    enrollment_year = forms.IntegerField(label="入学年")

    class Meta:
        model = User
        fields = ("email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 学科は有効なものだけ（フォーム生成のたびに最新を取る）
        self.fields["department"].queryset = Department.objects.filter(is_active=True)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        domain = email.rsplit("@", 1)[-1]
        if domain not in settings.ALLOWED_EMAIL_DOMAINS:
            raise forms.ValidationError("このメールアドレスのドメインは登録できません。")
        return email

    def clean_student_no(self):
        student_no = self.cleaned_data["student_no"]
        if Student.objects.filter(student_no=student_no).exists():
            raise forms.ValidationError("この学籍番号はすでに登録されています。")
        return student_no

    def clean_enrollment_year(self):
        year = self.cleaned_data["enrollment_year"]
        this_year = date.today().year
        if not (this_year - 10 <= year <= this_year):
            raise forms.ValidationError("入学年が正しくありません。")
        return year

    def clean(self):
        cleaned = super().clean()
        # TODO: 学籍番号と入学年の整合性チェック
        # TODO: メールアドレスからSlack IDを取得（取得できなければ再入力）
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.STUDENT
        user.save()
        Student.objects.create(
            user=user,
            student_no=self.cleaned_data["student_no"],
            student_name=self.cleaned_data["student_name"],
            department=self.cleaned_data["department"],
            enrollment_year=self.cleaned_data["enrollment_year"],
        )
        return user