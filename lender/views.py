from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

import base64
import io
import json
import re
import xml.etree.ElementTree as ET

import requests
from django.http import JsonResponse


# 貸借PCの流れ: standby → isbn_scan → user_auth(QR) → finish
# ※ await は Python の予約語なので、await.html の view 名は standby にしている

SCAN_TITLES = {
    "loan": "借りたい本のISBNを読み込んでください",
    "return": "返却する本のISBNを読み込んでください",
}

def standby(request):
    return render(request, "lender/await.html") 

def isbn_scan(request, mode):
    return render(request, "lender/isbn_typing.html", {   # テンプレートは実際のパスに合わせる
            "mode": mode,
            "page_title": SCAN_TITLES[mode],
        })
 
def qr_scan(request, mode):
    return render(request, "lender/qr_scan.html", {"mode": mode})

def user_auth(request):
    return render(request, "lender/user_auth.html")

def finish(request):
    return render(request, "lender/finish.html")


@require_POST
def cancel(request):
    # TODO: セッションの取引情報を破棄する
    return redirect("lender:standby")


FIELDS = ("isbn", "title", "author", "edition_year", "cover")
WANTED = ("title", "author", "edition_year", "cover")   # これらがそろえば追加の問い合わせをしない

def _year(s):
    """'20260505' '2026-05-05' '2026.5' '2026' → '2026'。年が取れなければ空文字"""
    m = re.search(r"\d{4}", str(s or ""))
    return m.group() if m else ""


def _isbn13_ok(isbn13):
    """ISBN-13の末尾のチェックデジットが正しいか"""
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(isbn13[:12]))
    return isbn13[12] == str((10 - total % 10) % 10)


def isbn10_to_13(isbn10):
    core = "978" + isbn10[:9]
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core))
    return core + str((10 - total % 10) % 10)


def normalize_isbn(raw):
    """ハイフンや空白を除き、ISBN-13に統一する。不正なら None"""
    s = raw.replace("-", "").replace(" ", "").upper()
    if len(s) == 10 and s[:9].isdigit() and (s[9].isdigit() or s[9] == "X"):
        return isbn10_to_13(s)
    if len(s) == 13 and s.isdigit() and s[:3] in ("978", "979") and _isbn13_ok(s):
        return s
    return None


def _openbd_lookup(isbn):
    try:
        res = requests.get(
            "https://api.openbd.jp/v1/get",
            params={"isbn": isbn},
            timeout=5,
        )
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError):
        return {}
    if not data or data[0] is None:
        return {}

    summary = data[0].get("summary") or {}
    return {
        "isbn": summary.get("isbn"),
        "title": summary.get("title"),
        "author": summary.get("author"),
        "edition_year": _year(summary.get("pubdate")),
        "cover": summary.get("cover") or "",
    }


def _local(tag):
    return tag.rsplit("}", 1)[-1]          # 名前空間を除いたタグ名


def _ndl_lookup(isbn):
    """NDLサーチ(SRU)をISBNで検索する。見つからなければ {}"""
    try:
        res = requests.get(
            "https://ndlsearch.ndl.go.jp/api/sru",
            params={
                "operation": "searchRetrieve",
                "query": f'isbn="{isbn}"',
                "maximumRecords": 1,
                "recordSchema": "dc",
                "recordPacking": "xml",
            },
            timeout=5,
        )
        res.raise_for_status()
        root = ET.fromstring(res.content)
    except (requests.RequestException, ET.ParseError):
        return {}

    record = next((e for e in root.iter() if _local(e.tag) == "recordData"), None)
    if record is None:
        return {}

    values = {}
    for e in record.iter():
        text = (e.text or "").strip()
        if text:
            values.setdefault(_local(e.tag), []).append(text)

    return {
        "title": (values.get("title") or [""])[0],
        "author": "、".join(values.get("creator", [])),
        "edition_year": _year((values.get("date") or values.get("issued") or [""])[0]),
    }


def _google_books_lookup(isbn):
    try:
        res = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}"},
            timeout=5,
        )
        res.raise_for_status()
        items = res.json().get("items") or []
    except (requests.RequestException, ValueError):
        return {}
    if not items:
        return {}

    info = items[0].get("volumeInfo") or {}
    links = info.get("imageLinks") or {}                                  
    cover = links.get("thumbnail") or links.get("smallThumbnail") or ""
    return {
        "title": info.get("title", ""),
        "author": "、".join(info.get("authors") or []),
        "edition_year": _year(info.get("publishedDate")),
        "cover": cover.replace("http://", "https://"),                    
    }


def book_info(request, isbn):
    isbn = normalize_isbn(isbn)
    if not isbn:
        return JsonResponse({"error": "ISBNの形式が正しくありません"}, status=400)

    details = _openbd_lookup(isbn)
    sources = ["OpenBD"] if details else []

    for name, lookup in (("NDLサーチ", _ndl_lookup), ("Google Books", _google_books_lookup)):
        if all(details.get(k) for k in WANTED):
            break                      # そろっていれば、以降は問い合わせない
        extra = lookup(isbn)
        filled = False
        for key, value in extra.items():
            if value and not details.get(key):
                details[key] = value
                filled = True
        if filled:
            sources.append(name)

    if not details.get("title"):
        return JsonResponse({"error": "本が見つかりませんでした"}, status=404)

    for key in FIELDS:
        details.setdefault(key, "")
    details["isbn"] = details["isbn"] or isbn
    details["sources"] = sources
    return JsonResponse(details)
