import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

# 学校のメール形式: 下の名前のイニシャル.名字.学科略称+入学年2桁@ドメイン
# 例: y.sasaki.sys25@morijyobi.ac.jp
#   y      … 下の名前のイニシャル（英字1文字）
#   sasaki … 名字（英字1文字以上）
#   sys    … 学科略称（英字1文字以上）
#   25     … 入学年の下2桁（@ の直前の数字2文字）
STUDENT_LOCAL_PART_RE = re.compile(
    r"^(?P<initial>[a-z])\.(?P<surname>[a-z]+)\.(?P<dept>[a-z]+)(?P<year>\d{2})$"
)


def normalize_student_email(email):
    """生徒のメールアドレスを検証し、小文字にして返す。問題があれば ValidationError。"""
    email = (email or "").strip().lower()
    if not email:
        raise ValidationError("メールアドレスを入力してください。")

    try:
        validate_email(email)
    except ValidationError:
        raise ValidationError("メールアドレスの形式が正しくありません。")

    local_part, domain = email.rsplit("@", 1)
    if domain not in settings.ALLOWED_EMAIL_DOMAINS:
        raise ValidationError("学校のメールアドレスを入力してください。")

    if not STUDENT_LOCAL_PART_RE.match(local_part):
        raise ValidationError(
            "メールアドレスは「名前のイニシャル.名字.学科入学年」の形式"
            "（例: y.sasaki.sys25@morijyobi.ac.jp）で入力してください。"
        )

    return email


def email_enrollment_year_suffix(email):
    """メールアドレスに含まれる入学年の下2桁（例: '25'）。取れなければ None。"""
    local_part = email.rsplit("@", 1)[0]
    match = STUDENT_LOCAL_PART_RE.match(local_part)
    return match.group("year") if match else None
