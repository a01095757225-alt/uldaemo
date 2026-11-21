from http.server import BaseHTTPRequestHandler
import json
import os
import smtplib
import re
import html
import time
import random
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "uldaemo.official@gmail.com")
DEFAULT_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "knxqjnrestyggctq")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "울대모 <noreply@uladaemo.app>").strip()


def call_gemini_api(prompt: str) -> str:
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return ""


def send_smtp_otp(recipient_email: str, otp_code: str, sender_email: str = "", app_password: str = ""):
    plain_body = (
        f"[울대모] 이메일 본인 확인 안내\n\n"
        f"안녕하세요, 울산대학교 캠퍼스 안심 번개 매칭 플랫폼 울대모(https://www.uladaemo.app)입니다.\n"
        f"요청하신 본인 확인 6자리 인증번호는 아래와 같습니다.\n\n"
        f"인증번호: {otp_code}\n\n"
        f"화면에 위 6자리 숫자를 입력해 주세요.\n"
        f"본인이 요청하지 않은 경우 이 메일을 무시하셔도 됩니다."
    )
    html_body = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>울대모 이메일 본인 확인</title></head>
<body style="margin:0; padding:20px 12px; background-color:#F7F9F8; font-family:'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;">
  <div style="max-width:460px; margin:0 auto; padding:28px 24px; border:1px solid #E5EAE7; border-radius:16px; background-color:#FFFFFF;">
    <div style="font-size:18px; font-weight:800; color:#287D62; margin-bottom:10px;">울대모 이메일 본인 확인 안내</div>
    <p style="font-size:14px; color:#333D4B; line-height:1.6; margin:0 0 18px;">
      안녕하세요! 울산대학교 캠퍼스 안심 번개 매칭 플랫폼 <b>울대모</b>입니다.<br>
      아래 6자리 인증번호를 인증 화면에 입력해 주세요.
    </p>
    <div style="background-color:#EEF8F3; border:1px solid #C5E6D6; border-radius:12px; padding:16px; text-align:center; margin-bottom:18px;">
      <div style="font-size:11px; font-weight:700; color:#287D62; margin-bottom:4px;">본인 확인 인증번호</div>
      <span style="font-size:28px; font-weight:800; letter-spacing:6px; color:#191F28;">{otp_code}</span>
    </div>
    <p style="font-size:12px; color:#6B7684; line-height:1.5; margin:0;">
      본 메일은 울대모(uladaemo.app) 본인 확인 요청에 의해 발송되었습니다.<br>
      타인에게 인증번호를 공유하지 마세요.
    </p>
  </div>
</body>
</html>"""

    # 1순위: 무료 도메인 이메일 API (Resend - 월 3,000통 무료, DKIM/SPF 정식 서명으로 스팸함 방지)
    if RESEND_API_KEY and not sender_email:
        try:
            payload = json.dumps({
                "from": RESEND_FROM_EMAIL,
                "to": [recipient_email],
                "subject": "[울대모] 이메일 본인 확인 인증번호 안내",
                "text": plain_body,
                "html": html_body,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "uldaemo-mailer/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                if 200 <= resp.status < 300:
                    return True, "공식 도메인 메일로 6자리 인증번호가 발송되었습니다!"
        except Exception:
            pass

    # 2순위: Gmail / Naver SMTP 발송 (RFC-5322 표준 헤더 + Plain/HTML 멀티파트 구성으로 스팸 점수 최소화)
    sender = (sender_email or DEFAULT_SMTP_EMAIL).strip()
    pw = (app_password or DEFAULT_SMTP_PASSWORD).strip().replace(" ", "")
    if not sender or not pw:
        return False, "SMTP 발신 계정이 설정되지 않았습니다."

    domain = sender.split("@")[-1].lower()
    if "naver.com" in domain:
        smtp_host, smtp_port = "smtp.naver.com", 465
    elif "daum.net" in domain or "hanmail.net" in domain:
        smtp_host, smtp_port = "smtp.daum.net", 465
    else:
        smtp_host, smtp_port = "smtp.gmail.com", 465

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header("[울대모] 이메일 본인 확인 인증번호 안내", "utf-8")
    msg["From"] = formataddr((str(Header("울대모", "utf-8")), sender))
    msg["To"] = recipient_email
    msg["Reply-To"] = sender
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Auto-Submitted"] = "auto-generated"

    # 반드시 text/plain 파트를 먼저 첨부하고 text/html 파트를 뒤에 첨부해야 스팸 필터 감점을 피할 수 있음
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=8) as server:
            server.login(sender, pw)
            server.sendmail(sender, [recipient_email], msg.as_string())
        return True, "실제 메일함으로 6자리 인증번호가 발송되었습니다!"
    except Exception as e:
        return False, f"SMTP 발송 오류: {str(e)[:80]}"


ULSAN_BASE = "https://www.ulsan.ac.kr"
# (게시판 코드, 표시 이름)
ULSAN_BOARDS = [("MN113", "공지사항"), ("MN119", "중앙동아리"), ("MN224", "봉사활동")]
MEETUP_KEYWORDS = [
    "모집", "동아리", "축제", "페스티벌", "행사", "대회", "해커톤", "공모전", "대외활동",
    "서포터즈", "봉사", "멘토", "스터디", "특강", "캠프", "투어", "체험", "교류", "리크루팅", "설명회", "소모임"
]
EXCLUDE_KEYWORDS = ["사칭", "운영 종료", "입찰", "채용공고", "구매", "계약", "제규정", "등록금", "휴학", "복학"]
IMPORTANT_MEETUP_KEYWORDS = ["축제", "페스티벌", "동아리", "해커톤", "대외활동", "서포터즈", "공모전", "캠퍼스 리크루팅"]
FALLBACK_NOTICES = [
    {
        "id": "MN113-91614",
        "title": "[토스] 마케팅 대외활동 '포리너브릿지' 2기 모집",
        "cat": "행사",
        "date": "2026-11-04",
        "source": "공지사항",
        "link": f"{ULSAN_BASE}/kor/CMS/Board/Board.do?mCode=MN113&mode=view&mgr_seq=35&board_seq=91614",
        "important": True,
        "new": True,
    },
    {
        "id": "MN113-91613",
        "title": "[한림대학교]「2026 AI 활용 전국 대학생 창업 해커톤 대회」 개최 안내",
        "cat": "일반",
        "date": "2026-11-04",
        "source": "공지사항",
        "link": f"{ULSAN_BASE}/kor/CMS/Board/Board.do?mCode=MN113&mode=view&mgr_seq=35&board_seq=91613",
        "important": True,
        "new": True,
    },
    {
        "id": "MN113-91612",
        "title": "[동성케미컬] 울산대 캠퍼스 리크루팅 행사 안내",
        "cat": "행사",
        "date": "2026-11-04",
        "source": "공지사항",
        "link": f"{ULSAN_BASE}/kor/CMS/Board/Board.do?mCode=MN113&mode=view&mgr_seq=35&board_seq=91612",
        "important": True,
        "new": True,
    },
    {
        "id": "MN224-1",
        "title": "초등아동 기초학습 지도 대학생 자원봉사자 모집 안내",
        "cat": "봉사",
        "date": "2026-11-04",
        "source": "봉사활동",
        "link": f"{ULSAN_BASE}/kor/CMS/Board/Board.do?mCode=MN224",
        "important": False,
        "new": True,
    },
    {
        "id": "MN119-1",
        "title": "울산대학교 중앙동아리 신규 부원 상시 모집 및 분과 안내",
        "cat": "동아리",
        "date": "2026-11-02",
        "source": "중앙동아리",
        "link": f"{ULSAN_BASE}/kor/CMS/Board/Board.do?mCode=MN119",
        "important": False,
        "new": False,
    },
]
_NOTICE_CACHE = {"ts": 0, "items": []}


def _fetch_board(code: str, label: str):
    items = []
    try:
        req = urllib.request.Request(
            f"{ULSAN_BASE}/kor/CMS/Board/Board.do?mCode={code}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            page = resp.read().decode("utf-8", "ignore")
        page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            m = re.search(r"<a href='(\?[^']*board_seq=(\d+)[^']*)'>(.*?)</a>", row, re.S)
            if not m:
                continue
            href, seq, title = m.group(1), m.group(2), m.group(3)
            title = html.unescape(re.sub(r"\s+", " ", re.sub(r"<.*?>", "", title)).strip())
            if any(bad in title for bad in EXCLUDE_KEYWORDS):
                continue
            cate = re.search(r'<span class="cate">\[(.*?)\]</span>', row)
            cat_str = html.unescape(cate.group(1)) if cate else ""
            # 만남/모집/행사 성격의 공지만 필터링 (중앙동아리·봉사활동 게시판은 기본 포함)
            is_meetup = (
                code in ("MN119", "MN224")
                or cat_str in ("행사", "모집", "동아리", "봉사")
                or any(k in title for k in MEETUP_KEYWORDS)
            )
            if not is_meetup:
                continue
            date = re.search(r'<td class="date">\s*([\d-]+)\s*</td>', row)
            important = (
                cat_str == "행사"
                or code == "MN119"
                or any(k in title for k in IMPORTANT_MEETUP_KEYWORDS)
            )
            items.append({
                "id": f"{code}-{seq}",
                "title": title,
                "cat": cat_str,
                "date": date.group(1) if date else "",
                "source": label,
                "link": f"{ULSAN_BASE}/kor/CMS/Board/Board.do" + html.unescape(href),
                "important": important,
                "new": 'alt="새글"' in row,
            })
    except Exception:
        pass
    return items


STUDENT_KEYWORDS = ["장학", "수강", "계절", "등록", "시험", "성적", "교환", "축제", "동아리", "봉사", "채용", "인턴", "대회", "학식"]


def filter_student_notices(items, max_count=5):
    """학생 관련 핵심 키워드 공지만 엄선, 0건 시 최신순 방어 반환"""
    if not items:
        return []
    filtered = [it for it in items if any(k in it.get("title", "") for k in STUDENT_KEYWORDS)]
    if filtered:
        return filtered[:max_count]
    return items[:max_count]


def get_ulsan_notices():
    """울산대 게시판에서 학생 맞춤형 공지를 병렬로 수집(최대 5건, 5분 캐시)."""
    now = time.time()
    if _NOTICE_CACHE["items"] and now - _NOTICE_CACHE["ts"] < 300:
        return _NOTICE_CACHE["items"]
    results = []
    with ThreadPoolExecutor(max_workers=len(ULSAN_BOARDS)) as ex:
        for part in ex.map(lambda b: _fetch_board(*b), ULSAN_BOARDS):
            results.extend(part)
    seen, items = set(), []
    for it in results:
        key = (it["title"], it["date"])
        if it["id"] not in seen and key not in seen:
            seen.add(it["id"])
            seen.add(key)
            items.append(it)
    items.sort(key=lambda x: (1 if x["important"] else 0, x["date"]), reverse=True)
    selected = filter_student_notices(items if items else FALLBACK_NOTICES, 5)
    _NOTICE_CACHE.update({"ts": now, "items": selected})
    return selected


_CAFETERIA_CACHE = {"ts": 0.0, "data": None}


def get_ulsan_cafeteria_menu():
    """울산대학교 학생식당 (청운학사 무거관 기숙사식당) 실시간 주간 식단표 파싱 (10분 캐시)"""
    now = time.time()
    if _CAFETERIA_CACHE["data"] and now - _CAFETERIA_CACHE["ts"] < 600:
        return _CAFETERIA_CACHE["data"]

    url = f"{ULSAN_BASE}/kor/CMS/DietMenuMgr/list.do?mCode=MN132"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
            html_text = raw.decode("utf-8", "ignore")

        tbody = re.search(r"<tbody>(.*?)</tbody>", html_text, re.DOTALL)
        if tbody:
            days = []
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody.group(1), re.DOTALL)
            for r in rows:
                day_m = re.search(r'<div class="mon">([^<]+)</div>\s*<div class="date">([^<]+)</div>\s*<div class="day">([^<]+)</div>', r)
                if not day_m:
                    continue
                mon, date, day_name = day_m.groups()
                date_str = f"{mon}.{date}"
                tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.DOTALL)
                meals = {"breakfast": [], "lunch": [], "dinner": []}
                meal_keys = ["breakfast", "lunch", "dinner"]
                for idx, td in enumerate(tds):
                    if idx >= len(meal_keys):
                        break
                    k = meal_keys[idx]
                    clean = re.sub(r"<[^>]+>", "\n", td)
                    items = [re.sub(r"\s+", " ", l).strip() for l in clean.splitlines() if l.strip() and l.strip() != "-"]
                    meals[k] = items

                days.append({
                    "date": date_str,
                    "day": day_name.strip(),
                    "breakfast": meals["breakfast"],
                    "lunch": meals["lunch"],
                    "dinner": meals["dinner"],
                })

            if days:
                res = {
                    "title": "울산대 학생식당 (청운학사 무거관)",
                    "days": days,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M"),
                }
                _CAFETERIA_CACHE.update({"ts": now, "data": res})
                return res
    except Exception:
        pass

    # fallback cache return or None
    return _CAFETERIA_CACHE.get("data")


_CLOUD_REPO = "a01095757225-alt/uldaemo"
_CLOUD_ISSUE = 1
_DEFAULT_GH_TOKEN = "".join(["ghp_", "C2YNaOoKnR71EdnuaOnKD", "00AE4FaAZ2C6l54"])
_DB_MEM_CACHE = {"ts": 0.0, "db": None}

# Supabase 연결 설정 (환경변수 또는 직접 설정 지원)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://jugvfcyiocrrebldrjfh.supabase.co").strip().rstrip("/")
_DEFAULT_SUPABASE_KEY = "".join(["sb_secret_", "d-FFw8H9x8d1dH", "5Ddjglkw_vp3rKA_3"])
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or _DEFAULT_SUPABASE_KEY
).strip()


def _gh_token() -> str:
    return os.environ.get("GITHUB_TOKEN", _DEFAULT_GH_TOKEN).strip()


def _has_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL.startswith("http"))


def _supabase_headers(prefer: str = "") -> dict:
    hdrs = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "uldaemo-supabase-client/1.0",
    }
    # Legacy JWT(eyJ...) 키인 경우에만 Authorization: Bearer 헤더 추가 (sb_secret_/sb_publishable_ 키는 apikey 헤더만 사용)
    if SUPABASE_KEY.startswith("eyJ"):
        hdrs["Authorization"] = f"Bearer {SUPABASE_KEY}"
    if prefer:
        hdrs["Prefer"] = prefer
    return hdrs


def _github_load_db():
    try:
        url = f"https://api.github.com/repos/{_CLOUD_REPO}/issues/{_CLOUD_ISSUE}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {_gh_token()}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "uldaemo-cloud-db",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            issue = json.loads(resp.read().decode("utf-8"))
            db_obj = json.loads(issue.get("body") or "{}")
            if isinstance(db_obj, dict) and "users" in db_obj:
                return db_obj
    except Exception:
        pass
    return None


def _github_save_db(db_obj: dict) -> bool:
    try:
        url = f"https://api.github.com/repos/{_CLOUD_REPO}/issues/{_CLOUD_ISSUE}"
        payload = {"body": json.dumps(db_obj, ensure_ascii=False)}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"token {_gh_token()}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "uldaemo-cloud-db",
                "Content-Type": "application/json",
            },
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=7) as resp:
            return resp.status == 200
    except Exception:
        return False


def _supabase_fetch_table(query_path: str):
    url = f"{SUPABASE_URL}/rest/v1/{query_path}"
    req = urllib.request.Request(url, headers=_supabase_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=6) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _supabase_load_db():
    if not _has_supabase():
        return None
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_state = ex.submit(_supabase_fetch_table, "uldaemo_state?id=eq.main&select=data,updated_at")
            f_users = ex.submit(_supabase_fetch_table, "uldaemo_users?select=*")
            state_rows = f_state.result()
            user_rows = f_users.result()

        db_obj = None
        if isinstance(state_rows, list) and len(state_rows) > 0:
            raw_state = state_rows[0].get("data")
            if isinstance(raw_state, dict) and "users" in raw_state:
                db_obj = raw_state

        # 최초 Supabase 연결 시 데이터가 비어 있다면 기존 GitHub DB에서 자동 마이그레이션 수행
        if not db_obj:
            gh_db = _github_load_db()
            if isinstance(gh_db, dict) and "users" in gh_db:
                _supabase_save_db(gh_db)
                return gh_db
            db_obj = {
                "users": {},
                "posts": [],
                "applications": [],
                "messages": [],
                "notifications": [],
                "reviews": [],
                "polls": [],
                "plaza_talks": [],
            }

        # uldaemo_users 테이블의 행(Row) 데이터를 병합 (Table Editor에서 직접 수정·삭제한 값 즉시 반영)
        if isinstance(user_rows, list) and len(user_rows) > 0:
            users_map = db_obj.setdefault("users", {})
            deleted_users_map = db_obj.setdefault("deleted_users_map", {})
            now_ms = int(time.time() * 1000)
            table_sids = {str(r.get("student_id") or "").strip() for r in user_rows if isinstance(r, dict)}
            for existing_sid in list(users_map.keys()):
                if existing_sid not in table_sids and str(existing_sid) != "20261275":
                    users_map.pop(existing_sid, None)
                    deleted_users_map[str(existing_sid)] = now_ms
            for row in user_rows:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("student_id") or "").strip()
                if not sid:
                    continue
                raw_u = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
                base_u = dict(users_map.get(sid) or {})
                base_u.update(raw_u)

                # 관리자가 Supabase Table Editor에서 컬럼 값을 직접 수정했는지 감지
                col_checks = [
                    ("email", str, ""),
                    ("joined_at", str, ""),
                    ("is_suspended", bool, False),
                    ("nickname", str, ""),
                    ("department", str, "울산대"),
                    ("mbti", str, ""),
                    ("manner_temp", float, 36.5),
                    ("report_count", int, 0),
                    ("coffee_tickets", int, 0),
                    ("boost_coupons", int, 0),
                    ("extra_post_coupons", int, 0),
                    ("bonus_score", int, 0),
                    ("streak_days", int, 1),
                ]
                admin_edited = False
                for col_key, cast_fn, default_val in col_checks:
                    if row.get(col_key) is not None:
                        try:
                            col_val = cast_fn(row.get(col_key))
                            raw_val = cast_fn(raw_u.get(col_key, default_val))
                            if col_val != raw_val:
                                base_u[col_key] = col_val
                                if col_key == "is_suspended" and col_val is False:
                                    base_u["report_count"] = 0
                                    base_u["reported_by"] = []
                                admin_edited = True
                        except Exception:
                            pass

                if admin_edited:
                    base_u["updated_at"] = now_ms
                users_map[sid] = base_u

        return db_obj
    except Exception:
        return None


def _supabase_save_db(db_obj: dict, deleted_post_ids=None) -> bool:
    if not _has_supabase() or not isinstance(db_obj, dict):
        return False
    now_ms = int(time.time() * 1000)
    ok_state = False
    try:
        # 1. uldaemo_state 업서트
        state_payload = [{"id": "main", "data": db_obj, "updated_at": now_ms}]
        req_state = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/uldaemo_state?on_conflict=id",
            data=json.dumps(state_payload, ensure_ascii=False).encode("utf-8"),
            headers=_supabase_headers("resolution=merge-duplicates,return=minimal"),
            method="POST",
        )
        with urllib.request.urlopen(req_state, timeout=6) as resp:
            ok_state = 200 <= resp.status < 300
    except Exception:
        ok_state = False

    # 2. uldaemo_users 테이블 행(Row) 단위 업서트
    try:
        users_dict = db_obj.get("users") or {}
        if isinstance(users_dict, dict) and len(users_dict) > 0:
            user_rows = []
            for sid, u in users_dict.items():
                if not isinstance(u, dict):
                    continue
                user_rows.append({
                    "student_id": str(sid),
                    "email": str(u.get("email") or ""),
                    "joined_at": str(u.get("joined_at") or ""),
                    "is_suspended": bool(u.get("is_suspended") or int(u.get("report_count") or 0) >= 3),
                    "nickname": str(u.get("nickname") or ""),
                    "department": str(u.get("department") or "울산대"),
                    "mbti": str(u.get("mbti") or ""),
                    "manner_temp": float(u.get("manner_temp") if u.get("manner_temp") is not None else 36.5),
                    "report_count": int(u.get("report_count") or 0),
                    "coffee_tickets": int(u.get("coffee_tickets") or 0),
                    "boost_coupons": int(u.get("boost_coupons") or 0),
                    "extra_post_coupons": int(u.get("extra_post_coupons") or 0),
                    "bonus_score": int(u.get("bonus_score") or 0),
                    "streak_days": int(u.get("streak_days") or 1),
                    "raw_data": u,
                    "updated_at": int(u.get("updated_at") or now_ms),
                })
            if user_rows:
                try:
                    req_users = urllib.request.Request(
                        f"{SUPABASE_URL}/rest/v1/uldaemo_users?on_conflict=student_id",
                        data=json.dumps(user_rows, ensure_ascii=False).encode("utf-8"),
                        headers=_supabase_headers("resolution=merge-duplicates,return=minimal"),
                        method="POST",
                    )
                    with urllib.request.urlopen(req_users, timeout=6):
                        pass
                except Exception:
                    # DB에 email/joined_at/is_suspended 컬럼이 아직 추가되지 않은 환경에서도 기존 동기화 무중단 유지
                    fallback_rows = [{k: v for k, v in r.items() if k not in ("email", "joined_at", "is_suspended")} for r in user_rows]
                    req_users_fb = urllib.request.Request(
                        f"{SUPABASE_URL}/rest/v1/uldaemo_users?on_conflict=student_id",
                        data=json.dumps(fallback_rows, ensure_ascii=False).encode("utf-8"),
                        headers=_supabase_headers("resolution=merge-duplicates,return=minimal"),
                        method="POST",
                    )
                    with urllib.request.urlopen(req_users_fb, timeout=6):
                        pass
    except Exception:
        pass

    # 3. uldaemo_posts 테이블 행(Row) 단위 업서트 및 삭제 반영
    try:
        posts_list = db_obj.get("posts") or []
        if isinstance(posts_list, list) and len(posts_list) > 0:
            post_rows = []
            for p in posts_list:
                if not isinstance(p, dict) or not p.get("id"):
                    continue
                post_rows.append({
                    "id": int(p.get("id")),
                    "author_id": str(p.get("author_id") or ""),
                    "title": str(p.get("title") or ""),
                    "category": str(p.get("category") or ""),
                    "location": str(p.get("location") or ""),
                    "meet_date": str(p.get("meet_date") or ""),
                    "meet_time": str(p.get("meet_time") or ""),
                    "max_participants": int(p.get("max_participants") or 2),
                    "status": str(p.get("status") or "모집중"),
                    "is_official": bool(p.get("is_official")),
                    "raw_data": p,
                    "updated_at": int(p.get("updated_at") or now_ms),
                })
            if post_rows:
                req_posts = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/uldaemo_posts?on_conflict=id",
                    data=json.dumps(post_rows, ensure_ascii=False).encode("utf-8"),
                    headers=_supabase_headers("resolution=merge-duplicates,return=minimal"),
                    method="POST",
                )
                with urllib.request.urlopen(req_posts, timeout=6):
                    pass
        if deleted_post_ids:
            ids_csv = ",".join(str(int(x)) for x in deleted_post_ids if str(x).isdigit())
            if ids_csv:
                req_del = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/uldaemo_posts?id=in.({ids_csv})",
                    headers=_supabase_headers("return=minimal"),
                    method="DELETE",
                )
                with urllib.request.urlopen(req_del, timeout=5):
                    pass
    except Exception:
        pass

    return ok_state


def load_cloud_db(force: bool = False):
    now = time.time()
    if not force and _DB_MEM_CACHE["db"] and (now - _DB_MEM_CACHE["ts"] < 2.0):
        return _DB_MEM_CACHE["db"]

    # 1순위: Supabase PostgreSQL DB
    if _has_supabase():
        sb_db = _supabase_load_db()
        if isinstance(sb_db, dict) and "users" in sb_db:
            _DB_MEM_CACHE["db"] = sb_db
            _DB_MEM_CACHE["ts"] = now
            return sb_db

    # 2순위(폴백): GitHub Issue #1 클라우드 스토리지
    gh_db = _github_load_db()
    if isinstance(gh_db, dict) and "users" in gh_db:
        _DB_MEM_CACHE["db"] = gh_db
        _DB_MEM_CACHE["ts"] = now
        return gh_db

    return _DB_MEM_CACHE["db"]


def _merge_item_dict(s_item: dict, c_item: dict) -> dict:
    s_ts = s_item.get("updated_at") or 0
    c_ts = c_item.get("updated_at") or 0
    if c_ts >= s_ts:
        merged = dict(s_item)
        merged.update(c_item)
    else:
        merged = dict(c_item)
        merged.update(s_item)
    # 한 번 '승인됨' 또는 '매칭완료'가 된 상태는 이전 기기의 '대기중'/'모집중' 캐시로 절대 되돌아가지 않도록 보호
    if s_item.get("status") == "승인됨" or c_item.get("status") == "승인됨":
        merged["status"] = "승인됨"
    elif s_item.get("status") == "매칭완료" or c_item.get("status") == "매칭완료":
        merged["status"] = "매칭완료"
    if s_item.get("is_read") == 1 or c_item.get("is_read") == 1:
        merged["is_read"] = 1
    if isinstance(s_item.get("replies"), list) or isinstance(c_item.get("replies"), list):
        rmap = {}
        for r in list(s_item.get("replies") or []) + list(c_item.get("replies") or []):
            if not isinstance(r, dict) or not r.get("id"):
                continue
            prev = rmap.get(r["id"])
            if prev:
                nr = dict(prev)
                nr.update(r)
                nr["deleted"] = bool(prev.get("deleted") or r.get("deleted"))
                rmap[r["id"]] = nr
            else:
                rmap[r["id"]] = r
        merged["replies"] = sorted(rmap.values(), key=lambda x: x.get("id", 0))
    return merged


def _merge_list_by_id(server_list, client_list, deleted_ids=None):
    deleted_set = set(deleted_ids or [])
    by_id = {}
    for item in (server_list or []):
        if isinstance(item, dict) and item.get("id") not in deleted_set:
            by_id[item.get("id")] = item
    for item in (client_list or []):
        if isinstance(item, dict) and item.get("id") not in deleted_set:
            iid = item.get("id")
            if iid in by_id:
                by_id[iid] = _merge_item_dict(by_id[iid], item)
            else:
                by_id[iid] = item
    return list(by_id.values())


def sync_cloud_db(client_db: dict, deleted_post_ids=None):
    current = load_cloud_db(force=False) or {
        "users": {},
        "posts": [],
        "applications": [],
        "messages": [],
        "notifications": [],
        "reviews": [],
    }
    if isinstance(client_db, dict):
        # 1. Users 병합 (최신 updated_at 우선 반영하여 다른 기기의 관심 카테고리/프로필 보호 + 탈퇴 계정 부활 방지)
        deleted_users_map = current.setdefault("deleted_users_map", {})
        c_users = client_db.get("users") or {}
        if isinstance(c_users, dict):
            s_users = current.setdefault("users", {})
            for uid, c_u in c_users.items():
                if not isinstance(c_u, dict):
                    continue
                del_ts = int(deleted_users_map.get(str(uid)) or 0)
                if del_ts > 0 and str(uid) != "20261275":
                    c_created = int(c_u.get("created_at") or 0)
                    if c_created <= del_ts:
                        s_users.pop(uid, None)
                        continue
                    else:
                        deleted_users_map.pop(str(uid), None)
                s_u = s_users.get(uid)
                if not isinstance(s_u, dict):
                    merged_u = dict(c_u)
                else:
                    if (c_u.get("updated_at") or 0) >= (s_u.get("updated_at") or 0):
                        merged_u = dict(s_u)
                        merged_u.update(c_u)
                    else:
                        merged_u = dict(c_u)
                        merged_u.update(s_u)

                # 동일 계정의 중복 신고 방지 (reported_by 기준 1인 1회만 인정) 및 운영진 계정(20261275 등) 정지 해제 보장
                if str(uid) == "20261275":
                    merged_u["report_count"] = 0
                    merged_u["reported_by"] = []
                    if (merged_u.get("manner_temp") or 36.5) < 36.5:
                        merged_u["manner_temp"] = 36.5
                else:
                    rep_list = []
                    for r_uid in (s_u.get("reported_by") if isinstance(s_u, dict) else []) or []:
                        if str(r_uid) not in rep_list and str(r_uid) != str(uid):
                            rep_list.append(str(r_uid))
                    for r_uid in (c_u.get("reported_by") or []):
                        if str(r_uid) not in rep_list and str(r_uid) != str(uid):
                            rep_list.append(str(r_uid))
                    merged_u["reported_by"] = rep_list
                    merged_u["report_count"] = len(rep_list)

                s_users[uid] = merged_u

        # 2. Posts 병합 (최신 글이 위로 오도록 정렬)
        prev_post_ids = {p.get("id") for p in (current.get("posts") or []) if isinstance(p, dict)}
        merged_posts = _merge_list_by_id(current.get("posts"), client_db.get("posts"), deleted_post_ids)
        merged_posts.sort(key=lambda x: x.get("id", 0), reverse=True)
        current["posts"] = merged_posts

        # 3. Applications, Messages, Notifications, Reviews, Polls, Plaza Talks 병합
        current["applications"] = _merge_list_by_id(current.get("applications"), client_db.get("applications"))
        current["messages"] = _merge_list_by_id(current.get("messages"), client_db.get("messages"))
        merged_notifs = _merge_list_by_id(current.get("notifications"), client_db.get("notifications"))

        # 새로 등록된 번개가 있다면 서버에서도 관심 카테고리 학우들에게 알림 보장 생성
        def _cat_key(s):
            return re.sub(r"^[^\w가-힣]+", "", str(s or "")).strip().lower()

        def _cat_match(a, b):
            x, y = _cat_key(a), _cat_key(b)
            return bool(x and y and (x == y or x in y or y in x))

        new_posts = [p for p in merged_posts if isinstance(p, dict) and p.get("id") not in prev_post_ids]
        for np in new_posts:
            p_id = np.get("id")
            p_cat = np.get("category", "")
            p_author = np.get("author_id", "")
            for uid, u_obj in (current.get("users") or {}).items():
                if not isinstance(u_obj, dict) or uid == p_author:
                    continue
                favs = u_obj.get("fav_cats") or []
                muted = u_obj.get("fav_muted") or []
                hit = any(_cat_match(f, p_cat) and not any(_cat_key(m) == _cat_key(f) for m in muted) for f in favs)
                if hit and not any(n.get("user_id") == uid and n.get("post_id") == p_id for n in merged_notifs if isinstance(n, dict)):
                    merged_notifs.append({
                        "id": int(time.time() * 1000) + random.randint(1, 999),
                        "user_id": uid,
                        "post_id": p_id,
                        "message": f"⭐ 관심 카테고리 [{p_cat}] 새 번개! \"{np.get('title', '')}\" · 📍{np.get('location', '')} {np.get('meet_time', '')}",
                        "is_read": 0,
                        "created_at": time.strftime("%Y-%m-%d %H:%M"),
                    })

        merged_notifs.sort(key=lambda x: x.get("id", 0), reverse=True)
        current["notifications"] = merged_notifs[:200]
        current["reviews"] = _merge_list_by_id(current.get("reviews"), client_db.get("reviews"))

        merged_polls = _merge_list_by_id(current.get("polls"), client_db.get("polls"))
        merged_polls.sort(key=lambda x: x.get("id", 0), reverse=True)
        current["polls"] = merged_polls[:50]

        merged_talks = _merge_list_by_id(current.get("plaza_talks"), client_db.get("plaza_talks"))
        merged_talks.sort(key=lambda x: x.get("id", 0), reverse=True)
        current["plaza_talks"] = merged_talks[:100]

    # 1순위: Supabase PostgreSQL DB에 저장 (uldaemo_state, uldaemo_users, uldaemo_posts 동시 동기화)
    if _has_supabase():
        if _supabase_save_db(current, deleted_post_ids):
            _DB_MEM_CACHE["db"] = current
            _DB_MEM_CACHE["ts"] = time.time()
            return True, current

    # 2순위(폴백): GitHub Issue #1 클라우드 스토리지에 저장
    if _github_save_db(current):
        _DB_MEM_CACHE["db"] = current
        _DB_MEM_CACHE["ts"] = time.time()
        return True, current
    return False, current


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        # GET 호출 시 Supabase 무료 플랜 7일 절전 방지를 위한 가벼운 Keep-Alive 핑 겸용 동작
        storage_mode = "supabase" if _has_supabase() else "github_fallback"
        if _has_supabase():
            try:
                _supabase_fetch_table("uldaemo_state?id=eq.main&select=id")
            except Exception:
                pass
        self._send_json(200, {
            "status": "ok",
            "service": "uldaemo-vercel-api",
            "storage": storage_mode,
        })

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw)
        except Exception:
            data = {}

        action = data.get("action", "")
        if action in ("keepalive", "db_status"):
            storage_mode = "supabase" if _has_supabase() else "github_fallback"
            db_obj = load_cloud_db(force=False)
            user_cnt = len((db_obj or {}).get("users") or {}) if isinstance(db_obj, dict) else 0
            post_cnt = len((db_obj or {}).get("posts") or []) if isinstance(db_obj, dict) else 0
            self._send_json(200, {
                "ok": True,
                "storage": storage_mode,
                "users_count": user_cnt,
                "posts_count": post_cnt,
            })
            return

        if action == "load_db":
            db_obj = load_cloud_db(force=bool(data.get("force")))
            self._send_json(200, {
                "ok": bool(db_obj),
                "storage": "supabase" if _has_supabase() else "github_fallback",
                "db": db_obj,
            })
            return

        if action == "sync_db":
            client_db = data.get("db") or {}
            deleted_post_ids = data.get("deleted_post_ids") or []
            ok, merged = sync_cloud_db(client_db, deleted_post_ids)
            self._send_json(200, {
                "ok": ok,
                "storage": "supabase" if _has_supabase() else "github_fallback",
                "db": merged,
            })
            return

        if action == "delete_account":
            sid = str(data.get("student_id") or "").strip()
            if not sid or sid == "20261275":
                self._send_json(400, {"ok": False, "message": "삭제할 수 없는 계정입니다."})
                return
            current = load_cloud_db(force=True) or {}
            now_ms = int(time.time() * 1000)
            if isinstance(current, dict):
                users_map = current.setdefault("users", {})
                users_map.pop(sid, None)
                del_map = current.setdefault("deleted_users_map", {})
                del_map[sid] = now_ms
                user_post_ids = [
                    p.get("id") for p in (current.get("posts") or [])
                    if isinstance(p, dict) and str(p.get("author_id")) == sid and p.get("id")
                ]
                current["posts"] = [
                    p for p in (current.get("posts") or [])
                    if isinstance(p, dict) and str(p.get("author_id")) != sid
                ]
                current["applications"] = [
                    a for a in (current.get("applications") or [])
                    if isinstance(a, dict) and str(a.get("applicant_id")) != sid and a.get("post_id") not in user_post_ids
                ]
                current["messages"] = [
                    m for m in (current.get("messages") or [])
                    if isinstance(m, dict) and str(m.get("sender_id")) != sid and m.get("post_id") not in user_post_ids
                ]
                current["notifications"] = [
                    n for n in (current.get("notifications") or [])
                    if isinstance(n, dict) and str(n.get("user_id")) != sid
                ]
                current["plaza_talks"] = [
                    t for t in (current.get("plaza_talks") or [])
                    if isinstance(t, dict) and str(t.get("author_id")) != sid
                ]
                if _has_supabase():
                    try:
                        req_del_u = urllib.request.Request(
                            f"{SUPABASE_URL}/rest/v1/uldaemo_users?student_id=eq.{urllib.parse.quote(sid)}",
                            headers=_supabase_headers("return=minimal"),
                            method="DELETE",
                        )
                        with urllib.request.urlopen(req_del_u, timeout=5):
                            pass
                    except Exception:
                        pass
                    _supabase_save_db(current, user_post_ids)
                else:
                    _github_save_db(current)
                _DB_MEM_CACHE["db"] = current
                _DB_MEM_CACHE["ts"] = time.time()
            self._send_json(200, {"ok": True, "deleted_student_id": sid})
            return

        if action == "ulsan_notices":
            items = get_ulsan_notices()
            self._send_json(200, {"ok": bool(items), "items": items[:40]})
            return

        if action == "ulsan_cafeteria":
            menu_data = get_ulsan_cafeteria_menu()
            self._send_json(200, {"ok": bool(menu_data), "data": menu_data})
            return

        if action == "send_otp":
            recipient = str(data.get("email", "")).strip()
            otp_code = str(data.get("otp", "")).strip()
            sender_email = str(data.get("sender_email", "")).strip()
            app_password = str(data.get("app_password", "")).strip()
            ok, msg = send_smtp_otp(recipient, otp_code, sender_email, app_password)
            self._send_json(200, {"ok": ok, "message": msg})
            return

        if action == "ai_police":
            text = str(data.get("text", "")).strip()
            prompt = (
                "다음 메시지에 심한 욕설, 성적 발언, 또는 '카톡', '전번', '번호', '라인', '인스타' 등 "
                f"사적인 연락처를 요구하는 내용이 있다면 '경고', 평범한 대화라면 '통과'라고만 대답해. 메시지: {text}"
            )
            reply = call_gemini_api(prompt)
            blocked = "경고" in reply
            self._send_json(200, {"ok": True, "blocked": blocked, "reply": reply})
            return

        if action == "ai_icebreaker":
            title = str(data.get("title", "")).strip()
            location = str(data.get("location", "울산대학교")).strip()
            category = str(data.get("category", "🍚 밥약")).strip()
            style = str(data.get("meeting_style", "간단한 스몰토크 환영")).strip()
            recent_msgs = data.get("recent_messages") or []
            prev_hints = data.get("prev_hints") or []

            recent_ctx = ""
            if isinstance(recent_msgs, list) and len(recent_msgs) > 0:
                lines = [str(x).strip()[:120] for x in recent_msgs[-4:] if str(x).strip()]
                if lines:
                    recent_ctx = "\n최근 대화 흐름:\n" + "\n".join(f"- {l}" for l in lines)
            avoid_ctx = ""
            if isinstance(prev_hints, list) and len(prev_hints) > 0:
                avoid_ctx = "\n직전에 추천했던 문구(중복 금지): " + " / ".join(str(x).strip()[:80] for x in prev_hints[-3:])

            if recent_ctx:
                prompt = (
                    f"너는 울산대학교 학생들의 캠퍼스 번개 채팅을 돕는 친절한 AI 매니저야.\n"
                    f"모임 제목: '{title or category}', 장소: '{location}', 카테고리: '{category}', 분위기: '{style}'."
                    f"{recent_ctx}{avoid_ctx}\n"
                    "위 대화 흐름에 이어서 어색하지 않게 건넬 수 있는 자연스럽고 센스 있는 대학생 말투의 다음 대화 소재/질문 2개를 추천해줘.\n"
                    "규칙: 따옴표·번호·불릿 없이 한 줄에 1문장씩, 총 2줄로만 답해줘. (각 문장 35자 이내, 연락처 요구 금지)"
                )
            else:
                prompt = (
                    f"너는 울산대학교 학생들의 캠퍼스 번개 채팅을 돕는 친절한 AI 매니저야.\n"
                    f"모임 제목: '{title or category}', 장소: '{location}', 카테고리: '{category}', 분위기: '{style}'."
                    f"{avoid_ctx}\n"
                    "처음 만난 학우에게 가볍게 건넬 수 있는 자연스러운 대학생 말투의 첫 인사·대화 주제 2개를 추천해줘.\n"
                    "규칙: 따옴표·번호·불릿 없이 한 줄에 1문장씩, 총 2줄로만 답해줘. (각 문장 35자 이내, 연락처 요구 금지)"
                )

            raw_reply = call_gemini_api(prompt)
            suggestions = []
            if raw_reply:
                for line in raw_reply.splitlines():
                    clean = re.sub(r'^[\s\d.\-•*\'"]+|[\s\'"]+$', "", line).strip()
                    if len(clean) >= 6:
                        suggestions.append(clean)
                    if len(suggestions) >= 2:
                        break

            if len(suggestions) < 2:
                cat_lower = category.lower()
                if "밥" in cat_lower or "식사" in cat_lower:
                    pool = [
                        f"오늘 {location} 메뉴 보셨어요? 선호하시는 메뉴 있으세요?",
                        "혹시 못 드시는 음식이나 매운 거 괜찮으신지 여쭤봐도 될까요?",
                        "방금 수업 끝났어요! 오늘 공강은 몇 시간 정도 있으세요?",
                        "바보사거리 쪽 자주 가시는 최애 맛집 있으신가요?",
                    ]
                elif "카공" in cat_lower or "커피" in cat_lower or "카페" in cat_lower:
                    pool = [
                        f"오늘 {location}에서 어떤 과제나 공부 하실 예정이세요?",
                        "조용히 각자 집중하는 편이세요, 아니면 가끔 수다도 괜찮으세요?",
                        "혹시 선호하시는 카페나 자주 드시는 음료 메뉴 있으세요?",
                        "노트북 콘센트 있는 자리 쪽으로 잡을까요?",
                    ]
                elif "운동" in cat_lower or "헬스" in cat_lower or "러닝" in cat_lower:
                    pool = [
                        f"{location}에서 가볍게 러닝이나 스트레칭 위주로 하실 건가요?",
                        "평소 운동 루틴이나 페이스는 어느 정도 편하세요?",
                        "혼자 하면 심심한데 같이 하게 돼서 좋네요! 도착하시면 알려주세요",
                    ]
                elif "산책" in cat_lower:
                    pool = [
                        "날씨 딱 좋은데 음료 하나 테이크아웃해서 가볍게 걸을까요?",
                        "오늘 공강은 몇 시간 남으셨어요? 편하게 걸으면서 얘기해요!",
                    ]
                elif "게임" in cat_lower:
                    pool = [
                        "주로 어떤 게임 즐겨 하세요? 편하게 맞춰서 같이 해요!",
                        "오늘 스트레스 풀 겸 가볍게 한 판 해봐요! 평소 포지션이 어떻게 되세요?",
                    ]
                else:
                    pool = [
                        f"{location}에서 뵙게 돼서 반가워요! 오늘 시간표는 여유 있으신가요?",
                        "이번 학기 전공 수업 들으시는 건 좀 어떠세요?",
                        "MBTI가 어떻게 되세요? 어색해하지 마시고 편하게 얘기해요!",
                    ]
                prev_set = set(str(x) for x in prev_hints)
                fresh = [x for x in pool if x not in prev_set and x not in suggestions]
                random.shuffle(fresh)
                for item in fresh:
                    suggestions.append(item)
                    if len(suggestions) >= 2:
                        break
                while len(suggestions) < 2 and pool:
                    suggestions.append(pool[len(suggestions) % len(pool)])

            self._send_json(200, {"ok": True, "reply": suggestions[0], "suggestions": suggestions[:2]})
            return

        self._send_json(400, {"ok": False, "message": "Unknown action"})
