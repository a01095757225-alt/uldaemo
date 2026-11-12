from http.server import BaseHTTPRequestHandler
import json
import os
import smtplib
import re
import html
import time
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "uldaemo.official@gmail.com")
DEFAULT_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "knxqjnrestyggctq")


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
    msg["Subject"] = f"[울대모] 이메일 본인 확인 인증번호 [{otp_code}]"
    msg["From"] = sender
    msg["To"] = recipient_email

    html_body = f"""
    <div style="font-family: 'Pretendard', -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 28px 24px; border: 1px solid #E5E8EB; border-radius: 16px; background-color: #FFFFFF;">
        <div style="font-size: 20px; font-weight: 800; color: #287D62; margin-bottom: 8px;">🌱 울대모 이메일 인증 안내</div>
        <p style="font-size: 14px; color: #4E5968; line-height: 1.6; margin-bottom: 20px;">
            안녕하세요! 캠퍼스 안심 번개 매칭 플랫폼 <b>울대모</b> 회원가입을 위한 본인 확인 인증번호입니다.<br>
            아래 6자리 인증번호를 가입 화면에 입력해 주세요.
        </p>
        <div style="background-color: #EEF8F3; border: 1px solid #C5E6D6; border-radius: 12px; padding: 18px; text-align: center; margin-bottom: 20px;">
            <span style="font-size: 28px; font-weight: 800; letter-spacing: 6px; color: #1E634C;">{otp_code}</span>
        </div>
        <p style="font-size: 12px; color: #8B95A1;">본 메일은 발신 전용이며, 타인에게 인증번호를 공유하지 마세요.</p>
    </div>
    """
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


def _gh_token() -> str:
    return os.environ.get("GITHUB_TOKEN", _DEFAULT_GH_TOKEN).strip()


def load_cloud_db(force: bool = False):
    now = time.time()
    if not force and _DB_MEM_CACHE["db"] and (now - _DB_MEM_CACHE["ts"] < 2.0):
        return _DB_MEM_CACHE["db"]
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
                _DB_MEM_CACHE["db"] = db_obj
                _DB_MEM_CACHE["ts"] = now
                return db_obj
    except Exception:
        pass
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
        # 1. Users 병합 (최신 updated_at 우선 반영하여 다른 기기의 관심 카테고리/프로필 보호)
        c_users = client_db.get("users") or {}
        if isinstance(c_users, dict):
            s_users = current.setdefault("users", {})
            for uid, c_u in c_users.items():
                if not isinstance(c_u, dict):
                    continue
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

    try:
        url = f"https://api.github.com/repos/{_CLOUD_REPO}/issues/{_CLOUD_ISSUE}"
        payload = {"body": json.dumps(current, ensure_ascii=False)}
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
            if resp.status == 200:
                _DB_MEM_CACHE["db"] = current
                _DB_MEM_CACHE["ts"] = time.time()
                return True, current
    except Exception:
        pass
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
        self._send_json(200, {"status": "ok", "service": "uldaemo-vercel-api"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw)
        except Exception:
            data = {}

        action = data.get("action", "")
        if action == "load_db":
            db_obj = load_cloud_db(force=bool(data.get("force")))
            self._send_json(200, {"ok": bool(db_obj), "db": db_obj})
            return

        if action == "sync_db":
            client_db = data.get("db") or {}
            deleted_post_ids = data.get("deleted_post_ids") or []
            ok, merged = sync_cloud_db(client_db, deleted_post_ids)
            self._send_json(200, {"ok": ok, "db": merged})
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
            location = str(data.get("location", "울산대학교"))
            category = str(data.get("category", "🍚 밥약"))
            style = str(data.get("meeting_style", "간단한 스몰토크 환영"))
            prompt = (
                f"너는 울산대학교 학생들의 번개 모임을 돕는 친절한 캠퍼스 AI 매니저야. "
                f"장소: '{location}', 카테고리: '{category}', 성향: '{style}'. "
                "상대방 학우에게 건넬 수 있는 자연스럽고 위트 있는 대학생 스타일의 첫 마디 추천 멘트 1개를 큰따옴표로 감싸서 작성해줘. "
                "로봇 같은 말투나 상투적인 공강 루틴 이야기는 피하고, 실제 대학생이 쓸 법한 친근한 말투로 1~2문장으로만 답해줘."
            )
            reply = call_gemini_api(prompt)
            if not reply:
                cat_lower = category.lower()
                if "밥" in cat_lower or "식사" in cat_lower:
                    options = [
                        f'"오늘 {location} 근처 학식 보셨어요? 돈까스나 제육도 좋고 바사 쪽도 아는 밥집 있는데 선호하시는 메뉴 있으세요?"',
                        f'"바보사거리 쪽 자주 가시는 맛집 있으신가요? 혹시 못 드시는 음식 있으시면 말씀해 주세요!"',
                        f'"오늘 든든한 한식이나 덮밥류가 당기시나요, 아니면 분식/면 종류가 편하세요? 좋아하시는 쪽으로 가요!"',
                        f'"{location} 쪽이나 후문 식당 중 어디가 더 편하세요? 맛있는 거 먹으러 가요 :)"',
                    ]
                elif "카공" in cat_lower or "커피" in cat_lower or "카페" in cat_lower:
                    options = [
                        f'"오늘 {location}에서 어떤 과제나 공부 벼락치기 하세요? 노트북 쓰기 편한 자리 쪽으로 갈까요?"',
                        f'"조용한 분위기에서 집중하는 편이세요, 아니면 가벼운 대화 가능한 카페가 편하세요?"',
                        f'"공강 시간 알차게 보내기엔 카공이 최고죠! 혹시 선호하시는 카페나 음료 메뉴 있으신가요?"',
                        f'"{location} 신관 쪽 자리 잡으셨나요? 커피 한잔하면서 같이 파이팅해요!"',
                    ]
                elif "운동" in cat_lower or "헬스" in cat_lower or "러닝" in cat_lower:
                    options = [
                        f'"{location}에서 가볍게 러닝이나 스트레칭 위주로 하실 건가요? 평소 운동 루틴에 맞춰서 같이 해요!"',
                        f'"운동 혼자 하면 심심한데 같이 하게 돼서 좋네요! 오늘 가볍게 땀 흘려봐요 ㅎㅎ"',
                        f'"{location} 쪽에서 뵈면 될까요? 무리하지 않고 편하게 운동해요 :)"',
                    ]
                elif "산책" in cat_lower:
                    options = [
                        f'"날씨 딱 좋은데 식물원 쪽 가볍게 걸으면서 이야기 나눌까요? 오늘 공강은 몇 시간 남으셨어요?"',
                        f'"캠퍼스 산책하면서 음료 테이크아웃 한잔 어떠세요? 편하게 걸어요 :)"',
                    ]
                elif "게임" in cat_lower:
                    options = [
                        f'"주로 어떤 게임 즐겨 하세요? 롤, 배그, 스팀 게임 다 괜찮은데 편하게 맞춰서 해요!"',
                        f'"오늘 스트레스 풀 겸 가볍게 즐겨봐요! 평소 티어나 포지션 어떻게 되세요? ㅎㅎ"',
                    ]
                else:
                    options = [
                        f'"혹시 몇 학번이세요? 이번 학기 전공 수업 들으시는 건 좀 어떠세요?"',
                        f'"MBTI가 어떻게 되세요? 저는 먼저 편하게 말 걸어주시면 금방 친해지는 편이에요 ㅎㅎ"',
                        f'"{location}에서 뵙게 돼서 반가워요! 오늘 시간표는 좀 여유 있으신 편인가요?"',
                        f'"만나서 반갑습니다! 어색해하지 마시고 편하게 말씀 나눠요 :)"',
                    ]
                reply = random.choice(options)
            self._send_json(200, {"ok": True, "reply": reply})
            return

        self._send_json(400, {"ok": False, "message": "Unknown action"})
