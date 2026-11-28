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
import urllib.error
import hmac
import hashlib
import base64
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DEFAULT_SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "uldaemo.official@gmail.com")
DEFAULT_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "울대모 <noreply@uladaemo.app>").strip()
SESSION_SECRET = (
    os.environ.get("SESSION_SECRET")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("GITHUB_TOKEN")
    or "uldaemo-dev-session-secret-only"
).encode("utf-8")

# 전화번호·SNS 아이디·외부 연락처 탐지 정규식 (서버·클라이언트 공통 보안 기준)
CONTACT_BANNED_KEYWORDS = (
    "카톡", "카카오", "카카오톡", "톡디", "전번", "전화번호", "폰번", "연락처",
    "오픈채팅", "옵챗", "인스타", "인스타그램", "디엠", "라인", "디스코드",
    "텔레그램", "텔그", "페북", "페이스북", "kakao", "kakaotalk", "open.kakao",
    "insta", "instagram", "discord", "telegram",
)
CONTACT_PHONE_RE = re.compile(r"(?:01[016789]|공일공)[\s.\-]*\d{3,4}[\s.\-]*\d{4}")
CONTACT_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
CONTACT_SNS_HANDLE_RE = re.compile(r"(?:^|\s)@[a-zA-Z0-9_.]{3,30}\b|(?:ig|id|카톡|인스타)\s*[:=]\s*[a-zA-Z0-9_.]{3,30}", re.I)
CONTACT_SOLICIT_RE = re.compile(r"(?:번호|폰|아이디|계정|연락)\s*(?:좀|알려|교환|줘|주실|주세요|뭐|어떻게|보내|남겨)", re.I)
ULSAN_UNIV_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@(?:mail\.)?ulsan\.ac\.kr$", re.I)

# 로그인·OTP 시도 횟수 제한 (학번 + IP 기준 슬라이딩 윈도우, 메모리 기반)
_AUTH_RATE_BUCKETS = {}
_AUTH_RATE_WINDOW_SEC = 600
_AUTH_MAX_SID_IP_FAILS = 5
_AUTH_MAX_IP_FAILS = 20
_OTP_MAX_PER_WINDOW = 5


def _prune_rate_bucket(key: str, now_ts: float):
    arr = _AUTH_RATE_BUCKETS.get(key)
    if not arr:
        return []
    cutoff = now_ts - _AUTH_RATE_WINDOW_SEC
    pruned = [t for t in arr if t > cutoff]
    if pruned:
        _AUTH_RATE_BUCKETS[key] = pruned
    else:
        _AUTH_RATE_BUCKETS.pop(key, None)
    return pruned


def _check_rate_limit(key: str, limit: int):
    now_ts = time.time()
    arr = _prune_rate_bucket(key, now_ts)
    if len(arr) >= limit:
        retry_after = max(1, int(_AUTH_RATE_WINDOW_SEC - (now_ts - arr[0])))
        return False, retry_after
    return True, 0


def _record_rate_hit(key: str):
    now_ts = time.time()
    arr = _prune_rate_bucket(key, now_ts)
    arr.append(now_ts)
    _AUTH_RATE_BUCKETS[key] = arr


def _clear_rate_bucket(key: str):
    _AUTH_RATE_BUCKETS.pop(key, None)


def _contains_contact_info(text: str) -> bool:
    t = str(text or "")
    tl = t.lower()
    if any(k in tl for k in CONTACT_BANNED_KEYWORDS):
        return True
    if CONTACT_PHONE_RE.search(t) or CONTACT_EMAIL_RE.search(t) or CONTACT_SNS_HANDLE_RE.search(t) or CONTACT_SOLICIT_RE.search(t):
        return True
    return False


def _strip_html_tags(text: str) -> str:
    s = str(text or "")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def _is_admin_user(u) -> bool:
    return isinstance(u, dict) and str(u.get("role") or "user").strip().lower() == "admin"


def _make_session_token(student_id: str, role: str = "user") -> str:
    exp = int(time.time()) + 30 * 24 * 3600
    r = "admin" if str(role).lower() == "admin" else "user"
    payload = f"{str(student_id).strip()}|{exp}|{r}"
    sig = hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}|{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _verify_session_token(token: str, expected_sid: str = ""):
    if not token or not isinstance(token, str):
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        parts = decoded.split("|")
        if len(parts) != 4:
            return None
        sid, exp_str, role_flag, sig = parts
        if int(exp_str) < int(time.time()):
            return None
        expected_sig = hmac.new(
            SESSION_SECRET,
            f"{sid}|{exp_str}|{role_flag}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        if expected_sid and str(sid) != str(expected_sid).strip():
            return None
        return {"student_id": sid, "role": "admin" if role_flag in ("1", "admin") else "user"}
    except Exception:
        return None


def _make_otp_token(email: str, otp: str) -> str:
    exp = int(time.time()) + 600
    norm_email = str(email or "").strip().lower()
    payload = f"otp|{norm_email}|{str(otp).strip()}|{exp}"
    sig = hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{exp}|{sig}".encode("utf-8")).decode("ascii")


def _verify_otp_token(token: str, email: str, otp: str) -> bool:
    if not token or not email or not otp:
        return False
    try:
        decoded = base64.urlsafe_b64decode(str(token).encode("ascii")).decode("utf-8")
        exp_str, sig = decoded.split("|", 1)
        if int(exp_str) < int(time.time()):
            return False
        norm_email = str(email).strip().lower()
        payload = f"otp|{norm_email}|{str(otp).strip()}|{exp_str}"
        expected = hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def _mask_uid(uid: str, viewer_id: str = "") -> str:
    s = str(uid or "").strip()
    if not s or s == "AI_BOT":
        return s
    if viewer_id and s == str(viewer_id).strip():
        return s
    digest = hmac.new(SESSION_SECRET, f"pub:{s}".encode("utf-8"), hashlib.sha256).hexdigest()[:10]
    return f"u_{digest}"


def _resolve_uid(raw_id: str, users_dict: dict) -> str:
    s = str(raw_id or "").strip()
    if not s:
        return ""
    if s in (users_dict or {}):
        return s
    if s.startswith("u_"):
        for real_uid in (users_dict or {}).keys():
            if _mask_uid(real_uid) == s:
                return str(real_uid)
    return s


def _sanitize_db_for_viewer(db_obj: dict, viewer_id: str = "", is_admin: bool = False):
    if not isinstance(db_obj, dict):
        return None
    vid = str(viewer_id or "").strip()
    if not vid:
        return None

    raw_posts = [p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and p.get("id") not in (101, 102, 103)]
    apps = [a for a in (db_obj.get("applications") or []) if isinstance(a, dict)]
    msgs = [m for m in (db_obj.get("messages") or []) if isinstance(m, dict)]
    notifs = [n for n in (db_obj.get("notifications") or []) if isinstance(n, dict)]
    reviews = [r for r in (db_obj.get("reviews") or []) if isinstance(r, dict)]
    polls = [pl for pl in (db_obj.get("polls") or []) if isinstance(pl, dict)]
    talks = [t for t in (db_obj.get("plaza_talks") or []) if isinstance(t, dict)]
    users = db_obj.get("users") or {}

    # 1. 본인이 방장이거나 수락('승인됨')된 모임 ID 및 활성 파트너 ID 계산 (운영진 예외 없음)
    hosted_post_ids = set()
    accepted_post_ids = set()
    active_accepted_post_ids = set()
    pending_host_ids = set()
    approved_counts = {}
    posts_by_id = {}
    for p in raw_posts:
        pid = p.get("id")
        if pid is None:
            continue
        ipid = int(pid)
        posts_by_id[ipid] = p
        if str(p.get("author_id") or "") == vid:
            hosted_post_ids.add(ipid)
            accepted_post_ids.add(ipid)
            if str(p.get("status") or "모집중") == "모집중":
                active_accepted_post_ids.add(ipid)
    for a in apps:
        pid = a.get("post_id")
        if pid is None:
            continue
        ipid = int(pid)
        st_a = str(a.get("status") or "")
        if st_a == "승인됨":
            approved_counts[ipid] = approved_counts.get(ipid, 0) + 1
            if str(a.get("applicant_id") or "") == vid:
                accepted_post_ids.add(ipid)
                p_obj = posts_by_id.get(ipid)
                if p_obj and str(p_obj.get("status") or "모집중") == "모집중":
                    active_accepted_post_ids.add(ipid)
        elif st_a == "대기중" and str(a.get("applicant_id") or "") == vid:
            p_obj = posts_by_id.get(ipid)
            if p_obj:
                pending_host_ids.add(str(p_obj.get("author_id") or ""))

    accepted_partner_ids = {vid}
    for p in raw_posts:
        pid = p.get("id")
        if pid is not None and int(pid) in active_accepted_post_ids:
            accepted_partner_ids.add(str(p.get("author_id") or ""))
    for a in apps:
        pid = a.get("post_id")
        if pid is not None and int(pid) in active_accepted_post_ids and a.get("status") == "승인됨":
            accepted_partner_ids.add(str(a.get("applicant_id") or ""))
    # 신청 대기중(status='대기중')인 번개의 방장은 운영진 예외 없이 항상 비공개 처리
    accepted_partner_ids -= pending_host_ids
    accepted_partner_ids.add(vid)

    def pub_id(uid: str) -> str:
        return _mask_uid(uid, vid)

    def _public_verified_badges(u_obj: dict):
        badges = []
        if str(u_obj.get("email") or "").strip():
            badges.append("학교 인증")
        if int(u_obj.get("report_count") or 0) == 0:
            badges.append("노쇼 ZERO")
        if float(u_obj.get("manner_temp") if u_obj.get("manner_temp") is not None else 36.5) >= 38.0:
            badges.append("따뜻한 매너")
        return badges

    # 2. 회원 응답 필터링 (일반 학생·관리자 공통):
    #    - 본인: 본인 프로필 전체(pw_hash 제외, role/report_count/bonus_score/streak_days 포함)
    #    - 타인(신청 대기중 포함 미승인 상태): nickname, avatar, manner_temp, verified_badges만
    #      (role, report_count, bonus_score, streak_days, department, mbti, bio, keywords, email, gender, student_id 제외)
    #    - 타인(승인됨 파트너): department, mbti, bio, keywords만 추가 공개
    safe_users = {}
    for uid, u in users.items():
        if not isinstance(u, dict):
            continue
        uid_str = str(uid)
        if uid_str == vid:
            su = dict(u)
            su["has_pw"] = bool(u.get("pw_hash"))
            su["role"] = "admin" if _is_admin_user(u) else "user"
            su["verified_badges"] = _public_verified_badges(u)
            su.pop("pw_hash", None)
            safe_users[vid] = su
        else:
            alias = _mask_uid(uid_str, vid)
            su = {
                "nickname": str(u.get("nickname") or "학우"),
                "avatar": str(u.get("avatar") or "🐶"),
                "manner_temp": float(u.get("manner_temp") if u.get("manner_temp") is not None else 36.5),
                "verified_badges": _public_verified_badges(u),
            }
            if uid_str in accepted_partner_ids:
                su["department"] = str(u.get("department") or "울산대")
                su["mbti"] = str(u.get("mbti") or "모름/비공개")
                su["bio"] = str(u.get("bio") or "")
                su["keywords"] = list(u.get("keywords") or [])
            safe_users[alias] = su

    # 3. 번개: 공개 필드만 반환 + 작성자 ID 별칭화 + 수락 인원수(accepted_count) 포함
    safe_posts = []
    for p in raw_posts:
        pid = p.get("id")
        ipid = int(pid) if pid is not None else 0
        safe_posts.append({
            "id": pid,
            "author_id": pub_id(p.get("author_id")),
            "title": str(p.get("title") or ""),
            "category": str(p.get("category") or ""),
            "location": str(p.get("location") or ""),
            "meet_date": str(p.get("meet_date") or ""),
            "meet_time": str(p.get("meet_time") or ""),
            "max_participants": int(p.get("max_participants") or 2),
            "accepted_count": 1 + approved_counts.get(ipid, 0),
            "meeting_style": str(p.get("meeting_style") or ""),
            "status": str(p.get("status") or "모집중"),
            "is_official": bool(p.get("is_official")),
            "is_boosted": bool(p.get("is_boosted")),
            "boosted_at": p.get("boosted_at"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
        })

    # 4. 신청 내역: 내가 신청한 건과 내가 만든 번개에 들어온 건만 반환
    safe_apps = []
    for a in apps:
        pid = a.get("post_id")
        ipid = int(pid) if pid is not None else 0
        ap_id = str(a.get("applicant_id") or "")
        if ap_id == vid or ipid in hosted_post_ids:
            safe_apps.append({
                "id": a.get("id"),
                "post_id": pid,
                "applicant_id": pub_id(ap_id),
                "status": str(a.get("status") or "대기중"),
                "updated_at": a.get("updated_at"),
            })

    # 5. 채팅: 수락된 참여자(방장 포함)에게만 해당 방 메시지 반환 (관리자 일반 응답에도 타인 방 메시지 미포함)
    safe_msgs = []
    for m in msgs:
        pid = m.get("post_id")
        if pid is None:
            continue
        ipid = int(pid)
        if ipid not in accepted_post_ids:
            continue
        if vid in [str(u) for u in (m.get("hidden_for") or [])]:
            continue
        is_del_all = bool(m.get("deleted_all"))
        sm = {
            "id": m.get("id"),
            "post_id": pid,
            "sender_id": "AI_BOT" if m.get("sender_id") == "AI_BOT" else pub_id(m.get("sender_id")),
            "text": "" if is_del_all else (_strip_html_tags(m.get("text")) if m.get("sender_id") == "AI_BOT" else str(m.get("text") or "")),
            "created_at": m.get("created_at"),
            "is_read": int(m.get("is_read") or 0),
            "edited": bool(m.get("edited")) and not is_del_all,
            "deleted_all": is_del_all,
            "reactions": {} if is_del_all else ({
                str(emo): [pub_id(u) for u in (arr or [])]
                for emo, arr in (m.get("reactions") or {}).items()
                if isinstance(arr, list)
            } if isinstance(m.get("reactions"), dict) else {}),
        }
        if not is_del_all and isinstance(m.get("reply_to"), dict):
            sm["reply_to"] = {
                "id": m["reply_to"].get("id"),
                "sender_label": str(m["reply_to"].get("sender_label") or "")[:24],
                "text_preview": str(m["reply_to"].get("text_preview") or "")[:60],
            }
        if m.get("flagged"):
            sm["flagged"] = True
        if m.get("sender_id") == "AI_BOT":
            sm["kind"] = str(m.get("kind") or "ai_icebreaker")
            if isinstance(m.get("suggestions"), list):
                sm["suggestions"] = [_strip_html_tags(x) for x in m["suggestions"]]
        safe_msgs.append(sm)

    # 6. 알림: 본인 알림만 반환 (관리자 동일 적용)
    safe_notifs = [
        n for n in notifs
        if str(n.get("user_id") or "") == vid
    ]

    # 7. 후기 · 투표 · 광장톡: 타인 학번 별칭화
    safe_reviews = []
    for r in reviews:
        sr = dict(r)
        sr["from_id"] = pub_id(r.get("from_id"))
        sr["to_id"] = pub_id(r.get("to_id"))
        safe_reviews.append(sr)

    safe_polls = []
    for pl in polls:
        sp = dict(pl)
        sp["votes_a"] = [pub_id(u) for u in (pl.get("votes_a") or [])]
        sp["votes_b"] = [pub_id(u) for u in (pl.get("votes_b") or [])]
        if isinstance(pl.get("replies"), list):
            sp["replies"] = [
                {
                    **rep,
                    "author_id": pub_id(rep.get("author_id")),
                    "likes": [pub_id(u) for u in (rep.get("likes") or [])],
                }
                for rep in pl["replies"] if isinstance(rep, dict)
            ]
        safe_polls.append(sp)

    safe_talks = []
    for t in talks:
        st = dict(t)
        st["author_id"] = pub_id(t.get("author_id"))
        st["likes"] = [pub_id(u) for u in (t.get("likes") or [])]
        if isinstance(t.get("replies"), list):
            st["replies"] = [
                {
                    **rep,
                    "author_id": pub_id(rep.get("author_id")),
                    "likes": [pub_id(u) for u in (rep.get("likes") or [])],
                }
                for rep in t["replies"] if isinstance(rep, dict)
            ]
        safe_talks.append(st)

    return {
        "users": safe_users,
        "posts": safe_posts,
        "deleted_post_ids": db_obj.get("deleted_post_ids") or [],
        "applications": safe_apps,
        "messages": safe_msgs,
        "notifications": safe_notifs,
        "reviews": safe_reviews,
        "polls": safe_polls,
        "plaza_talks": safe_talks,
    }


def _gemini_endpoint_candidates(models):
    key = (GEMINI_API_KEY or "").strip()
    q_key = urllib.parse.quote(key, safe="")
    return [
        (m, f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={q_key}")
        for m in models
    ]


def _scrub_secret(text: str) -> str:
    s = str(text or "")
    if GEMINI_API_KEY:
        s = s.replace(GEMINI_API_KEY, "***")
    return s


GEMINI_MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.8-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]


def _gemini_one_call(model_name, url, body_obj, timeout_sec):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body_obj).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        chunks = [str(p.get("text", "")) for p in parts if isinstance(p, dict) and p.get("text") and not p.get("thought")]
        txt = "\n".join(chunks).strip()
        if txt:
            return txt, ""
        return "", f"{model_name}:empty"
    except urllib.error.HTTPError as he:
        err_body = ""
        try:
            err_body = he.read().decode("utf-8", "ignore").replace("\n", " ")[:100]
        except Exception:
            pass
        return "", _scrub_secret(f"{model_name} HTTP {he.code}: {err_body}")
    except Exception as ex:
        return "", _scrub_secret(f"{model_name} {str(ex)[:80]}")


def _gemini_race(body_obj, validator=None, timeout_sec=6.5, models=None, prefer_non_lite=False):
    """여러 모델에 동시에 요청하고 유효한 응답을 사용 (Vercel 10초 제한 내 확실히 응답)."""
    from concurrent.futures import as_completed
    cands = _gemini_endpoint_candidates(models or GEMINI_MODEL_CANDIDATES)
    errs = []
    lite_fallback = None
    ex = ThreadPoolExecutor(max_workers=len(cands))
    try:
        fut_to_model = {ex.submit(_gemini_one_call, m, u, body_obj, timeout_sec): m for m, u in cands}
        deadline = time.time() + timeout_sec
        pending_non_lite = sum(1 for m, _ in cands if "lite" not in m)
        try:
            for fut in as_completed(list(fut_to_model.keys()), timeout=max(1.0, deadline - time.time())):
                m_name = fut_to_model[fut]
                is_lite = "lite" in m_name
                if not is_lite:
                    pending_non_lite = max(0, pending_non_lite - 1)
                txt, err = fut.result()
                if txt:
                    val = txt if validator is None else validator(txt)
                    if val is not None:
                        if prefer_non_lite and is_lite and pending_non_lite > 0 and (deadline - time.time()) > 1.2:
                            if lite_fallback is None:
                                lite_fallback = val
                            continue
                        return val, ""
                    errs.append(f"{m_name}:invalid_output")
                else:
                    errs.append(err)
                if lite_fallback is not None and pending_non_lite == 0:
                    return lite_fallback, ""
        except Exception:
            errs.append("race_timeout")
    finally:
        ex.shutdown(wait=False)
    if lite_fallback is not None:
        return lite_fallback, ""
    return None, " | ".join(errs)[:360]


def _call_gemini_text_with_diag(prompt: str):
    if not GEMINI_API_KEY:
        return "", "missing_key"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    val, err = _gemini_race(body, timeout_sec=6)
    return (val or ""), err


def call_gemini_api(prompt: str) -> str:
    txt, _ = _call_gemini_text_with_diag(prompt)
    return txt


def _parse_json_loose(txt):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(txt).strip())
    try:
        obj = json.loads(cleaned)
    except Exception:
        m_obj = re.search(r"\{[\s\S]*\}", cleaned)
        if not m_obj:
            return None
        try:
            obj = json.loads(m_obj.group(0))
        except Exception:
            return None
    return obj if isinstance(obj, dict) else None


def call_gemini_vision_json(prompt: str, image_b64: str, mime_type: str = "image/jpeg"):
    if not GEMINI_API_KEY or not image_b64:
        return None, "missing_key"
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": mime_type, "data": image_b64}},
            ],
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.05},
    }
    return _gemini_race(
        body,
        validator=_parse_json_loose,
        timeout_sec=6.5,
        models=["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.8-flash-lite", "gemini-flash-lite-latest"],
        prefer_non_lite=True,
    )


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


_CLOUD_REPO = os.environ.get("ULDAEMO_CLOUD_REPO", "a01095757225-alt/uldaemo")
_CLOUD_ISSUE = int(os.environ.get("ULDAEMO_CLOUD_ISSUE", "1"))
_DB_MEM_CACHE = {"ts": 0.0, "db": None}
LOCAL_TEST_DB_PATH = os.environ.get("ULDAEMO_LOCAL_TEST_DB", "").strip()

# Supabase 연결 설정 (환경변수 전용 — 코드 내 서비스 키 하드코딩 금지)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or ""
).strip()


def _gh_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip()


def _has_supabase() -> bool:
    return bool(not LOCAL_TEST_DB_PATH and SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL.startswith("http"))


def _local_test_load_db():
    if not LOCAL_TEST_DB_PATH:
        return None
    try:
        if os.path.exists(LOCAL_TEST_DB_PATH):
            with open(LOCAL_TEST_DB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "users" in data:
                    return data
    except Exception:
        pass
    return {
        "users": {},
        "posts": [],
        "deleted_post_ids": [],
        "applications": [],
        "messages": [],
        "notifications": [],
        "reviews": [],
        "polls": [],
        "plaza_talks": [],
    }


def _local_test_save_db(db_obj: dict) -> bool:
    if not LOCAL_TEST_DB_PATH:
        return False
    try:
        with open(LOCAL_TEST_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db_obj, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


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


def _supabase_load_db(include_users_table: bool = True):
    if not _has_supabase():
        return None
    try:
        if include_users_table:
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_state = ex.submit(_supabase_fetch_table, "uldaemo_state?id=eq.main&select=data,updated_at")
                f_users = ex.submit(_supabase_fetch_table, "uldaemo_users?select=*")
                state_rows = f_state.result()
                user_rows = f_users.result()
        else:
            state_rows = _supabase_fetch_table("uldaemo_state?id=eq.main&select=data,updated_at")
            user_rows = None

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
                if existing_sid not in table_sids and not _is_admin_user(users_map.get(existing_sid)):
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

                # 관리자가 Supabase Table Editor에서 컬럼 값을 직접 수정했는지 감지 (role 포함)
                col_checks = [
                    ("role", str, "user"),
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


def _supabase_save_db(db_obj: dict, deleted_post_ids=None, sync_users: bool = True, sync_posts: bool = True) -> bool:
    if not _has_supabase() or not isinstance(db_obj, dict):
        return False
    now_ms = int(time.time() * 1000)

    def _upsert_state():
        try:
            state_payload = [{"id": "main", "data": db_obj, "updated_at": now_ms}]
            req_state = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/uldaemo_state?on_conflict=id",
                data=json.dumps(state_payload, ensure_ascii=False).encode("utf-8"),
                headers=_supabase_headers("resolution=merge-duplicates,return=minimal"),
                method="POST",
            )
            with urllib.request.urlopen(req_state, timeout=6) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def _upsert_users():
        try:
            users_dict = db_obj.get("users") or {}
            if not isinstance(users_dict, dict) or not users_dict:
                return
            user_rows = []
            for sid, u in users_dict.items():
                if not isinstance(u, dict):
                    continue
                user_rows.append({
                    "student_id": str(sid),
                    "role": "admin" if _is_admin_user(u) else "user",
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
                    fallback_rows = [{k: v for k, v in r.items() if k not in ("role", "email", "joined_at", "is_suspended")} for r in user_rows]
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

    def _upsert_posts():
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
        except Exception:
            pass

    def _delete_posts():
        try:
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

    # 모든 테이블 업서트·삭제를 병렬 실행하여 응답 지연(RTT) 대폭 단축
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_state = ex.submit(_upsert_state)
        futs = []
        if sync_users:
            futs.append(ex.submit(_upsert_users))
        if sync_posts:
            futs.append(ex.submit(_upsert_posts))
        if deleted_post_ids:
            futs.append(ex.submit(_delete_posts))
        ok_state = f_state.result()
        for f in futs:
            try:
                f.result()
            except Exception:
                pass

    return ok_state


def load_cloud_db(force: bool = False, include_users_table: bool = True):
    if LOCAL_TEST_DB_PATH:
        return _local_test_load_db()
    now = time.time()
    if not force and _DB_MEM_CACHE["db"] and (now - _DB_MEM_CACHE["ts"] < 2.0):
        return _DB_MEM_CACHE["db"]

    # 1순위: Supabase PostgreSQL DB (설정되어 있으면 오래된 GitHub 스냅샷으로 절대 폴백하지 않음)
    if _has_supabase():
        sb_db = _supabase_load_db(include_users_table=include_users_table)
        if isinstance(sb_db, dict) and "users" in sb_db:
            _DB_MEM_CACHE["db"] = sb_db
            _DB_MEM_CACHE["ts"] = now
            return sb_db
        return _DB_MEM_CACHE["db"]

    # 2순위(Supabase 미설정 환경 전용): GitHub Issue #1 클라우드 스토리지
    gh_db = _github_load_db()
    if isinstance(gh_db, dict) and "users" in gh_db:
        _DB_MEM_CACHE["db"] = gh_db
        _DB_MEM_CACHE["ts"] = now
        return gh_db

    return _DB_MEM_CACHE["db"]


def save_cloud_db(db_obj: dict, deleted_post_ids=None, sync_users: bool = True, sync_posts: bool = True) -> bool:
    if LOCAL_TEST_DB_PATH:
        return _local_test_save_db(db_obj)
    if _has_supabase():
        all_del_ids = db_obj.get("deleted_post_ids") or deleted_post_ids or []
        if _supabase_save_db(db_obj, all_del_ids, sync_users=sync_users, sync_posts=sync_posts):
            _DB_MEM_CACHE["db"] = db_obj
            _DB_MEM_CACHE["ts"] = time.time()
            return True
        return False
    if _github_save_db(db_obj):
        _DB_MEM_CACHE["db"] = db_obj
        _DB_MEM_CACHE["ts"] = time.time()
        return True
    return False


# 보안 강화: 레거시 전체 DB 병합(sync_cloud_db / _merge_list_by_id / _merge_item_dict) 완전 삭제.
# 모든 상태 변경은 session_token 기반 전용 액션 API를 통해서만 서버가 직접 검증 후 저장합니다.


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

        def _require_auth(allow_suspended: bool = False, include_users_table: bool = False):
            tok = str(data.get("session_token") or "").strip()
            sess = _verify_session_token(tok)
            if not sess:
                self._send_json(401, {"ok": False, "error": "AUTH_REQUIRED", "message": "로그인이 필요합니다."})
                return None, None, False
            db_obj = load_cloud_db(force=True, include_users_table=include_users_table)
            if not isinstance(db_obj, dict):
                self._send_json(503, {"ok": False, "error": "DB_UNAVAILABLE", "message": "데이터베이스에 연결할 수 없습니다."})
                return None, None, False
            uid = str(sess["student_id"]).strip()
            actor = (db_obj.get("users") or {}).get(uid)
            if not isinstance(actor, dict):
                self._send_json(401, {"ok": False, "error": "INVALID_SESSION", "message": "유효하지 않은 세션입니다. 다시 로그인해주세요."})
                return None, None, False
            is_adm = _is_admin_user(actor)
            if not allow_suspended and not is_adm and (actor.get("is_suspended") or int(actor.get("report_count") or 0) >= 3):
                self._send_json(403, {"ok": False, "error": "ACCOUNT_SUSPENDED", "message": "이용이 정지된 계정입니다."})
                return None, None, False
            return db_obj, uid, is_adm

        def _add_notif(db_obj: dict, target_uid: str, message: str, post_id=None):
            if not target_uid or not message:
                return
            notifs = db_obj.setdefault("notifications", [])
            notifs.insert(0, {
                "id": int(time.time() * 1000) + random.randint(1, 999),
                "user_id": str(target_uid),
                "post_id": post_id,
                "message": str(message)[:240],
                "is_read": 0,
                "created_at": time.strftime("%Y-%m-%d %H:%M"),
            })
            db_obj["notifications"] = notifs[:200]

        def _finish_mutation(db_obj: dict, actor_id: str, is_adm: bool, extra=None, deleted_post_ids=None, sync_users=None, sync_posts=None):
            if sync_users is None:
                sync_users = action not in ("apply", "cancel_application", "accept", "reject", "send_message", "react_message", "mark_read", "edit_message", "delete_message", "mark_notifs_read", "mark_notifications_read", "plaza_create_poll", "plaza_create_talk", "plaza_like_talk", "plaza_reply", "plaza_delete_reply", "plaza_like_reply")
            if sync_posts is None:
                sync_posts = action in ("create_post", "cancel_post", "close_post", "boost_post", "leave_chat", "delete_account")
            ok = save_cloud_db(db_obj, deleted_post_ids, sync_users=sync_users, sync_posts=sync_posts)
            payload = {
                "ok": ok,
                "storage": "local_test" if LOCAL_TEST_DB_PATH else ("supabase" if _has_supabase() else "github_fallback"),
                "db": _sanitize_db_for_viewer(db_obj, actor_id, is_adm),
            }
            if isinstance(extra, dict):
                payload.update(extra)
            self._send_json(200 if ok else 500, payload)

        # 클라이언트 IP 추출 (학번+IP 기반 로그인 시도 횟수 제한용)
        fwd_for = str(self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        client_ip = fwd_for or str(self.headers.get("X-Real-IP") or "").strip() or str((self.client_address or ("unknown",))[0])

        # ---- 1) 공개 인증 API ----
        if action == "send_otp":
            recipient = str(data.get("email") or "").strip().lower()
            if not CONTACT_EMAIL_RE.match(recipient):
                self._send_json(400, {"ok": False, "message": "올바른 이메일 주소를 입력해주세요."})
                return
            ok_ip, retry_ip = _check_rate_limit(f"otp_ip:{client_ip}", _AUTH_MAX_IP_FAILS)
            ok_em, retry_em = _check_rate_limit(f"otp_em:{client_ip}:{recipient}", _OTP_MAX_PER_WINDOW)
            if not ok_ip or not ok_em:
                self._send_json(429, {
                    "ok": False,
                    "reason": "rate_limited",
                    "retry_after": max(retry_ip, retry_em),
                    "message": "인증번호 요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
                })
                return
            _record_rate_hit(f"otp_ip:{client_ip}")
            _record_rate_hit(f"otp_em:{client_ip}:{recipient}")
            otp_code = str(random.randint(100000, 999999))
            otp_token = _make_otp_token(recipient, otp_code)
            if LOCAL_TEST_DB_PATH:
                self._send_json(200, {"ok": True, "message": "테스트 모드 OTP 발급 완료", "otp_token": otp_token})
                return
            ok, msg = send_smtp_otp(recipient, otp_code)
            self._send_json(200, {"ok": ok, "message": msg, "otp_token": otp_token if ok else ""})
            return

        if action == "verify_login":
            sid = str(data.get("student_id") or "").strip()
            pw_hash = str(data.get("pw_hash") or "").strip()
            if not sid:
                self._send_json(400, {"ok": False, "reason": "missing_sid"})
                return
            rl_sid_key = f"login_sid:{client_ip}:{sid}"
            rl_ip_key = f"login_ip:{client_ip}"
            ok_sid, retry_sid = _check_rate_limit(rl_sid_key, _AUTH_MAX_SID_IP_FAILS)
            ok_ip, retry_ip = _check_rate_limit(rl_ip_key, _AUTH_MAX_IP_FAILS)
            if not ok_sid or not ok_ip:
                self._send_json(429, {
                    "ok": False,
                    "reason": "rate_limited",
                    "retry_after": max(retry_sid, retry_ip),
                    "message": "로그인 시도 횟수가 초과되었습니다. 10분 후 다시 시도해주세요.",
                })
                return
            db_obj = load_cloud_db(force=True) or {}
            user = (db_obj.get("users") or {}).get(sid)
            if not isinstance(user, dict):
                _record_rate_hit(rl_sid_key)
                _record_rate_hit(rl_ip_key)
                self._send_json(200, {"ok": False, "reason": "not_found"})
                return
            stored_hash = str(user.get("pw_hash") or "").strip()
            if not stored_hash:
                _record_rate_hit(rl_sid_key)
                _record_rate_hit(rl_ip_key)
                self._send_json(200, {"ok": False, "reason": "no_pw"})
                return
            if not pw_hash:
                _record_rate_hit(rl_sid_key)
                _record_rate_hit(rl_ip_key)
                self._send_json(200, {"ok": False, "reason": "missing_pw"})
                return
            if not hmac.compare_digest(stored_hash, pw_hash):
                _record_rate_hit(rl_sid_key)
                _record_rate_hit(rl_ip_key)
                self._send_json(200, {"ok": False, "reason": "wrong_pw"})
                return
            _clear_rate_bucket(rl_sid_key)
            is_adm = _is_admin_user(user)
            token = _make_session_token(sid, role="admin" if is_adm else "user")
            sanitized = _sanitize_db_for_viewer(db_obj, sid, is_adm)
            self._send_json(200, {
                "ok": True,
                "session_token": token,
                "role": "admin" if is_adm else "user",
                "db": sanitized,
            })
            return

        if action == "signup":
            sid = str(data.get("student_id") or "").strip()
            pw_hash = str(data.get("pw_hash") or "").strip()
            email = str(data.get("email") or "").strip().lower()
            otp_code = str(data.get("otp") or "").strip()
            otp_token = str(data.get("otp_token") or "").strip()
            nick = str(data.get("nickname") or "").strip()[:12]
            dept = str(data.get("department") or "").strip()[:24]
            avatar = str(data.get("avatar") or "🐶").split(" ")[0][:4]
            gender = str(data.get("gender") or "").strip()
            mbti = str(data.get("mbti") or "모름/비공개").strip()[:12]
            if not sid or len(sid) < 4 or len(sid) > 20:
                self._send_json(400, {"ok": False, "message": "올바른 학번을 입력해주세요."})
                return
            if not pw_hash or len(pw_hash) < 32:
                self._send_json(400, {"ok": False, "message": "비밀번호를 4자리 이상 설정해주세요."})
                return
            if not nick or not dept:
                self._send_json(400, {"ok": False, "message": "닉네임과 학과를 모두 입력해주세요."})
                return
            if not data.get("agree_age19") or not data.get("agree_terms") or not data.get("agree_privacy"):
                self._send_json(400, {"ok": False, "message": "필수 약관 및 만 19세 이상 확인에 동의해주세요."})
                return
            if not _verify_otp_token(otp_token, email, otp_code):
                self._send_json(403, {"ok": False, "message": "이메일 6자리 본인 인증이 유효하지 않거나 만료되었습니다."})
                return
            db_obj = load_cloud_db(force=True)
            if not isinstance(db_obj, dict):
                self._send_json(503, {"ok": False, "message": "서버 저장소에 연결할 수 없습니다."})
                return
            users = db_obj.setdefault("users", {})
            if sid in users:
                self._send_json(409, {"ok": False, "message": "이미 가입된 학번입니다. 로그인을 이용해주세요."})
                return
            now_ms = int(time.time() * 1000)
            joined_str = time.strftime("%Y-%m-%d %H:%M")
            users[sid] = {
                "student_id": sid,
                "role": "user",
                "email": email,
                "joined_at": joined_str,
                "created_at": now_ms,
                "age_19_verified": True,
                "agreed_terms_at": joined_str,
                "pw_hash": pw_hash,
                "nickname": nick,
                "avatar": avatar,
                "gender": gender,
                "department": dept,
                "mbti": mbti,
                "manner_temp": 36.5,
                "report_count": 0,
                "reported_by": [],
                "is_suspended": False,
                "bio": "반갑습니다! 공강 시간에 같이 소통해요.",
                "keywords": ["시간 약속을 잘 지켜요", "친절해요"],
                "coffee_tickets": 0,
                "boost_coupons": 0,
                "extra_post_coupons": 0,
                "bonus_score": 0,
                "streak_days": 1,
                "updated_at": now_ms,
            }
            if isinstance(db_obj.get("deleted_users_map"), dict):
                db_obj["deleted_users_map"].pop(sid, None)
            token = _make_session_token(sid, role="user")
            _finish_mutation(db_obj, sid, False, extra={"session_token": token, "role": "user"})
            return

        if action == "reset_password":
            sid = str(data.get("student_id") or "").strip()
            email = str(data.get("email") or "").strip().lower()
            otp_code = str(data.get("otp") or "").strip()
            otp_token = str(data.get("otp_token") or "").strip()
            new_pw_hash = str(data.get("pw_hash") or "").strip()
            rl_reset_key = f"reset_sid:{client_ip}:{sid}"
            ok_rs, retry_rs = _check_rate_limit(rl_reset_key, _AUTH_MAX_SID_IP_FAILS)
            if not ok_rs:
                self._send_json(429, {
                    "ok": False,
                    "reason": "rate_limited",
                    "retry_after": retry_rs,
                    "message": "비밀번호 설정 시도 횟수가 초과되었습니다. 10분 후 다시 시도해주세요.",
                })
                return
            if not sid or not new_pw_hash or len(new_pw_hash) < 32:
                _record_rate_hit(rl_reset_key)
                self._send_json(400, {"ok": False, "message": "학번과 새 비밀번호를 확인해주세요."})
                return
            if not _verify_otp_token(otp_token, email, otp_code):
                _record_rate_hit(rl_reset_key)
                self._send_json(403, {"ok": False, "message": "이메일 6자리 인증번호가 일치하지 않거나 만료되었습니다."})
                return
            db_obj = load_cloud_db(force=True)
            users_map = (db_obj.get("users") or {}) if isinstance(db_obj, dict) else {}
            user = users_map.get(sid)
            if not isinstance(user, dict):
                _record_rate_hit(rl_reset_key)
                self._send_json(404, {"ok": False, "message": "등록되지 않은 학번입니다."})
                return
            stored_email = str(user.get("email") or "").strip().lower()
            if stored_email:
                if stored_email != email:
                    _record_rate_hit(rl_reset_key)
                    self._send_json(403, {"ok": False, "message": "가입 시 등록한 이메일 주소와 일치하지 않습니다."})
                    return
            else:
                # 이메일 미등록(has_pw=false) 레거시 계정 선점 방지: 울산대 학교 메일(@ulsan.ac.kr) 본인 인증만 허용
                if not ULSAN_UNIV_EMAIL_RE.match(email):
                    _record_rate_hit(rl_reset_key)
                    self._send_json(403, {
                        "ok": False,
                        "message": "등록된 이메일이 없는 계정은 울산대학교 학교 메일(@ulsan.ac.kr) 본인 인증으로만 최초 비밀번호를 설정할 수 있습니다.",
                    })
                    return
                email_taken = any(
                    str(other_sid) != sid and isinstance(other_u, dict) and str(other_u.get("email") or "").strip().lower() == email
                    for other_sid, other_u in users_map.items()
                )
                if email_taken:
                    _record_rate_hit(rl_reset_key)
                    self._send_json(409, {"ok": False, "message": "이미 다른 계정에 등록된 학교 메일입니다."})
                    return
                user["email"] = email
            _clear_rate_bucket(rl_reset_key)
            _clear_rate_bucket(f"login_sid:{client_ip}:{sid}")
            user["pw_hash"] = new_pw_hash
            user["updated_at"] = int(time.time() * 1000)
            is_adm = _is_admin_user(user)
            token = _make_session_token(sid, role="admin" if is_adm else "user")
            _finish_mutation(db_obj, sid, is_adm, extra={"session_token": token, "role": "admin" if is_adm else "user"})
            return

        # ---- 2) 전체 동기화(sync_db) 영구 폐지 ----
        if action == "sync_db":
            self._send_json(410, {
                "ok": False,
                "error": "SYNC_DB_DISABLED",
                "message": "보안을 위해 전체 DB 동기화(sync_db)가 폐지되었습니다. 전용 API를 사용하세요.",
            })
            return

        # ---- 3) 공개 학교 정보 및 상태 점검 API ----
        if action == "health":
            db_probe = "no_config"
            if _has_supabase():
                try:
                    rows = _supabase_fetch_table("uldaemo_users?select=student_id&limit=1")
                    db_probe = f"ok_rows_{len(rows) if isinstance(rows, list) else 'nonlist'}"
                except urllib.error.HTTPError as he:
                    db_probe = f"http_{he.code}"
                except Exception as ex:
                    db_probe = f"err_{type(ex).__name__}"
            self._send_json(200, {
                "ok": True,
                "has_supabase": _has_supabase(),
                "url_ok": bool(SUPABASE_URL.startswith("https://") and ".supabase.co" in SUPABASE_URL),
                "key_prefix": "jwt" if SUPABASE_KEY.startswith("eyJ") else ("sb_secret" if SUPABASE_KEY.startswith("sb_secret_") else "other"),
                "key_len": len(SUPABASE_KEY),
                "db_probe": db_probe,
            })
            return

        if action == "ulsan_notices":
            items = get_ulsan_notices()
            self._send_json(200, {"ok": bool(items), "items": items[:40]})
            return

        if action == "ulsan_cafeteria":
            menu_data = get_ulsan_cafeteria_menu()
            self._send_json(200, {"ok": bool(menu_data), "data": menu_data})
            return

        # ---- 4) 인증 필수 조회 API (비로그인 호출 시 401 거부) ----
        if action == "load_db":
            db_obj, actor_id, is_adm = _require_auth(allow_suspended=True)
            if not db_obj:
                return
            self._send_json(200, {
                "ok": True,
                "storage": "local_test" if LOCAL_TEST_DB_PATH else ("supabase" if _has_supabase() else "github_fallback"),
                "role": "admin" if is_adm else "user",
                "db": _sanitize_db_for_viewer(db_obj, actor_id, is_adm),
            })
            return

        if action == "poll_chat":
            db_obj, actor_id, is_adm = _require_auth(allow_suspended=True, include_users_table=False)
            if not db_obj:
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 대화방 ID입니다."})
                return
            post = next((p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if not post:
                self._send_json(404, {"ok": False, "message": "대화방을 찾을 수 없습니다."})
                return
            is_member = (str(post.get("author_id")) == actor_id) or any(
                isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and str(a.get("applicant_id")) == actor_id and a.get("status") == "승인됨"
                for a in (db_obj.get("applications") or [])
            )
            if not is_member:
                self._send_json(403, {"ok": False, "message": "수락된 참여자만 이 대화방에 접근할 수 있습니다."})
                return
            room_msgs = []
            for m in (db_obj.get("messages") or []):
                if not isinstance(m, dict) or int(m.get("post_id") or 0) != post_id:
                    continue
                if actor_id in [str(u) for u in (m.get("hidden_for") or [])]:
                    continue
                is_del_all = bool(m.get("deleted_all"))
                sm = {
                    "id": m.get("id"),
                    "post_id": post_id,
                    "sender_id": "AI_BOT" if m.get("sender_id") == "AI_BOT" else _mask_uid(str(m.get("sender_id") or ""), actor_id),
                    "text": "" if is_del_all else (_strip_html_tags(m.get("text")) if m.get("sender_id") == "AI_BOT" else str(m.get("text") or "")),
                    "created_at": m.get("created_at"),
                    "is_read": int(m.get("is_read") or 0),
                    "edited": bool(m.get("edited")) and not is_del_all,
                    "deleted_all": is_del_all,
                    "reactions": {} if is_del_all else ({
                        str(emo): [_mask_uid(str(u), actor_id) for u in (arr or [])]
                        for emo, arr in (m.get("reactions") or {}).items()
                        if isinstance(arr, list)
                    } if isinstance(m.get("reactions"), dict) else {}),
                }
                if not is_del_all and isinstance(m.get("reply_to"), dict):
                    sm["reply_to"] = {
                        "id": m["reply_to"].get("id"),
                        "sender_label": str(m["reply_to"].get("sender_label") or "")[:24],
                        "text_preview": str(m["reply_to"].get("text_preview") or "")[:60],
                    }
                if m.get("sender_id") == "AI_BOT":
                    sm["kind"] = str(m.get("kind") or "ai_icebreaker")
                    if isinstance(m.get("suggestions"), list):
                        sm["suggestions"] = [_strip_html_tags(x) for x in m["suggestions"]]
                room_msgs.append(sm)
            self._send_json(200, {"ok": True, "post_id": post_id, "messages": room_msgs})
            return

        # ---- 5) 동작별 전용 API (모든 actor_id는 session_token에서만 추출) ----
        if action == "create_post":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            title = str(data.get("title") or "").strip()[:80]
            category = str(data.get("category") or "").strip()[:30]
            location = str(data.get("location") or "").strip()[:60]
            meet_date = str(data.get("meet_date") or "").strip()
            meet_time = str(data.get("meet_time") or "").strip()
            style = str(data.get("meeting_style") or "").strip()[:40]
            try:
                max_p = int(data.get("max_participants") or 3)
            except Exception:
                max_p = 3
            if len(title) < 2 or not category or not location or not meet_date or not meet_time:
                self._send_json(400, {"ok": False, "message": "필수 항목을 모두 입력해주세요."})
                return
            if max_p < 2 or max_p > 30:
                self._send_json(400, {"ok": False, "message": "모집 인원은 2명 이상 30명 이하로 설정해주세요."})
                return
            actor = db_obj["users"][actor_id]
            use_boost = False
            if data.get("use_boost") and int(actor.get("boost_coupons") or 0) > 0:
                actor["boost_coupons"] = max(0, int(actor.get("boost_coupons") or 0) - 1)
                use_boost = True
            now_ms = int(time.time() * 1000)
            new_post = {
                "id": now_ms,
                "author_id": actor_id,
                "title": title,
                "category": category,
                "meet_date": meet_date,
                "meet_time": meet_time,
                "location": location,
                "max_participants": max_p,
                "meeting_style": style or "가볍게 소통해요",
                "is_official": bool(is_adm and data.get("is_official")),
                "is_boosted": use_boost,
                "boosted_at": now_ms if use_boost else None,
                "status": "모집중",
                "created_at": now_ms,
                "updated_at": now_ms,
            }
            db_obj.setdefault("posts", []).insert(0, new_post)
            _finish_mutation(db_obj, actor_id, is_adm, extra={"post_id": now_ms})
            return

        if action in ("cancel_post", "close_post", "boost_post"):
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 번개 ID입니다."})
                return
            posts = db_obj.get("posts") or []
            post = next((p for p in posts if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if not post:
                self._send_json(404, {"ok": False, "message": "번개를 찾을 수 없습니다."})
                return
            if str(post.get("author_id")) != actor_id and not is_adm:
                self._send_json(403, {"ok": False, "message": "본인이 만든 번개만 수정/취소할 수 있습니다."})
                return
            now_ms = int(time.time() * 1000)
            deleted_ids = None
            if action == "cancel_post":
                post["status"] = "취소됨"
                post["updated_at"] = now_ms
                for a in (db_obj.get("applications") or []):
                    if isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and str(a.get("applicant_id")) != actor_id:
                        _add_notif(db_obj, a.get("applicant_id"), f"[{post.get('title')}] 번개 모임이 방장에 의해 취소되었어요.", post_id)
                del_list = list(db_obj.get("deleted_post_ids") or [])
                if post_id not in del_list:
                    del_list.append(post_id)
                db_obj["deleted_post_ids"] = del_list[-500:]
                db_obj["posts"] = [p for p in posts if isinstance(p, dict) and int(p.get("id") or 0) != post_id]
                deleted_ids = [post_id]
            elif action == "close_post":
                post["status"] = "매칭완료"
                post["updated_at"] = now_ms
            elif action == "boost_post":
                actor = db_obj["users"][actor_id]
                if int(actor.get("boost_coupons") or 0) <= 0:
                    self._send_json(400, {"ok": False, "message": "보유한 상단 부스트권이 없습니다."})
                    return
                actor["boost_coupons"] = int(actor.get("boost_coupons") or 0) - 1
                post["is_boosted"] = True
                post["boosted_at"] = now_ms
                post["updated_at"] = now_ms
            _finish_mutation(db_obj, actor_id, is_adm, deleted_post_ids=deleted_ids)
            return

        if action == "apply":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 번개 ID입니다."})
                return
            post = next((p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if not post or post.get("status") != "모집중":
                self._send_json(400, {"ok": False, "message": "모집 중인 번개가 아닙니다."})
                return
            if str(post.get("author_id")) == actor_id:
                self._send_json(400, {"ok": False, "message": "본인이 만든 번개에는 신청할 수 없습니다."})
                return
            apps = db_obj.setdefault("applications", [])
            approved_cnt = sum(1 for a in apps if isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and a.get("status") == "승인됨")
            if 1 + approved_cnt >= int(post.get("max_participants") or 2):
                self._send_json(400, {"ok": False, "message": "정원이 마감된 번개입니다."})
                return
            now_ms = int(time.time() * 1000)
            existing = next((a for a in apps if isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and str(a.get("applicant_id")) == actor_id), None)
            if existing:
                if existing.get("status") in ("취소됨", "나감"):
                    existing["status"] = "대기중"
                    existing["updated_at"] = now_ms
                else:
                    self._send_json(409, {"ok": False, "message": "이미 신청한 번개입니다."})
                    return
            else:
                apps.append({
                    "id": now_ms,
                    "post_id": post_id,
                    "applicant_id": actor_id,
                    "status": "대기중",
                    "updated_at": now_ms,
                })
            nick = db_obj["users"][actor_id].get("nickname") or "학우"
            _add_notif(db_obj, post.get("author_id"), f"[{post.get('title')}] 모임에 {nick}님이 참여를 신청했어요", post_id)
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action == "cancel_application":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 번개 ID입니다."})
                return
            app = next((a for a in (db_obj.get("applications") or []) if isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and str(a.get("applicant_id")) == actor_id and a.get("status") == "대기중"), None)
            if not app:
                self._send_json(404, {"ok": False, "message": "취소할 대기 중인 신청을 찾을 수 없습니다."})
                return
            app["status"] = "취소됨"
            app["updated_at"] = int(time.time() * 1000)
            post = next((p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if post:
                nick = db_obj["users"][actor_id].get("nickname") or "학우"
                _add_notif(db_obj, post.get("author_id"), f"[{post.get('title')}] 모임의 {nick}님이 참여 신청을 취소했어요", post_id)
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action in ("accept", "reject"):
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            try:
                app_id = int(data.get("app_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 신청 ID입니다."})
                return
            app = next((a for a in (db_obj.get("applications") or []) if isinstance(a, dict) and int(a.get("id") or 0) == app_id), None)
            if not app:
                self._send_json(404, {"ok": False, "message": "신청 내역을 찾을 수 없습니다."})
                return
            post_id = int(app.get("post_id") or 0)
            post = next((p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if not post or (str(post.get("author_id")) != actor_id and not is_adm):
                self._send_json(403, {"ok": False, "message": "해당 번개의 방장만 수락/거절할 수 있습니다."})
                return
            now_ms = int(time.time() * 1000)
            if action == "accept":
                app["status"] = "승인됨"
                app["updated_at"] = now_ms
                _add_notif(db_obj, app.get("applicant_id"), f"🎉 [{post.get('title')}] 참여 신청이 수락되었어요! 안심 대화방을 확인해 보세요.", post_id)
            else:
                app["status"] = "거절됨"
                app["updated_at"] = now_ms
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action == "leave_chat":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 번개 ID입니다."})
                return
            post = next((p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if not post:
                self._send_json(404, {"ok": False, "message": "대화방을 찾을 수 없습니다."})
                return
            now_ms = int(time.time() * 1000)
            if str(post.get("author_id")) == actor_id:
                post["status"] = "매칭완료"
                post["updated_at"] = now_ms
                for a in (db_obj.get("applications") or []):
                    if isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and a.get("status") == "승인됨":
                        a["status"] = "종료됨"
                        a["updated_at"] = now_ms
            else:
                for a in (db_obj.get("applications") or []):
                    if isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and str(a.get("applicant_id")) == actor_id:
                        a["status"] = "나감"
                        a["updated_at"] = now_ms
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action in ("send_message", "react_message", "mark_read", "edit_message", "delete_message"):
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 대화방 ID입니다."})
                return
            post = next((p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if not post:
                self._send_json(404, {"ok": False, "message": "대화방을 찾을 수 없습니다."})
                return
            is_member = (str(post.get("author_id")) == actor_id) or any(
                isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and str(a.get("applicant_id")) == actor_id and a.get("status") == "승인됨"
                for a in (db_obj.get("applications") or [])
            )
            if not is_member:
                self._send_json(403, {"ok": False, "message": "수락된 참여자만 이 대화방에 접근할 수 있습니다."})
                return
            now_ms = int(time.time() * 1000)
            if action == "send_message":
                txt = str(data.get("text") or "").strip()[:500]
                if not txt:
                    self._send_json(400, {"ok": False, "message": "메시지를 입력해주세요."})
                    return
                if _contains_contact_info(txt):
                    self._send_json(400, {"ok": False, "blocked": True, "message": "연락처는 만나서 직접 주고받아요. 지금은 앱 안에서만 이야기해요"})
                    return
                new_msg = {
                    "id": now_ms,
                    "post_id": post_id,
                    "sender_id": actor_id,
                    "text": txt,
                    "created_at": time.strftime("%H:%M"),
                    "is_read": 0,
                    "reactions": {},
                }
                raw_rt = data.get("reply_to")
                if isinstance(raw_rt, dict) and raw_rt.get("id"):
                    new_msg["reply_to"] = {
                        "id": raw_rt.get("id"),
                        "sender_label": str(raw_rt.get("sender_label") or "")[:24],
                        "text_preview": str(raw_rt.get("text_preview") or "")[:60],
                    }
                db_obj.setdefault("messages", []).append(new_msg)
                _finish_mutation(db_obj, actor_id, is_adm, extra={"message_id": now_ms})
                return
            elif action == "edit_message":
                try:
                    msg_id = int(data.get("message_id"))
                except Exception:
                    self._send_json(400, {"ok": False, "message": "잘못된 메시지 ID입니다."})
                    return
                new_txt = str(data.get("text") or "").strip()[:500]
                if not new_txt:
                    self._send_json(400, {"ok": False, "message": "수정할 내용을 입력해주세요."})
                    return
                if _contains_contact_info(new_txt):
                    self._send_json(400, {"ok": False, "blocked": True, "message": "연락처는 만나서 직접 주고받아요. 지금은 앱 안에서만 이야기해요"})
                    return
                msg = next((m for m in (db_obj.get("messages") or []) if isinstance(m, dict) and int(m.get("id") or 0) == msg_id and int(m.get("post_id") or 0) == post_id), None)
                if not msg or msg.get("deleted_all"):
                    self._send_json(404, {"ok": False, "message": "수정할 메시지를 찾을 수 없습니다."})
                    return
                if str(msg.get("sender_id")) != actor_id:
                    self._send_json(403, {"ok": False, "message": "본인이 보낸 메시지만 수정할 수 있습니다."})
                    return
                msg["text"] = new_txt
                msg["edited"] = True
                msg["updated_at"] = now_ms
                _finish_mutation(db_obj, actor_id, is_adm)
                return
            elif action == "delete_message":
                try:
                    msg_id = int(data.get("message_id"))
                except Exception:
                    self._send_json(400, {"ok": False, "message": "잘못된 메시지 ID입니다."})
                    return
                mode = str(data.get("mode") or "me").strip().lower()
                msg = next((m for m in (db_obj.get("messages") or []) if isinstance(m, dict) and int(m.get("id") or 0) == msg_id and int(m.get("post_id") or 0) == post_id), None)
                if not msg:
                    self._send_json(404, {"ok": False, "message": "삭제할 메시지를 찾을 수 없습니다."})
                    return
                if mode == "all":
                    if str(msg.get("sender_id")) != actor_id:
                        self._send_json(403, {"ok": False, "message": "본인이 보낸 메시지만 전체 삭제할 수 있습니다."})
                        return
                    msg["deleted_all"] = True
                    msg["text"] = ""
                    msg["reactions"] = {}
                    msg.pop("reply_to", None)
                    msg["updated_at"] = now_ms
                else:
                    hidden = [str(u) for u in (msg.get("hidden_for") or [])]
                    if actor_id not in hidden:
                        hidden.append(actor_id)
                    msg["hidden_for"] = hidden
                    msg["updated_at"] = now_ms
                _finish_mutation(db_obj, actor_id, is_adm)
                return
            elif action == "react_message":
                try:
                    msg_id = int(data.get("message_id"))
                except Exception:
                    self._send_json(400, {"ok": False})
                    return
                emoji = str(data.get("emoji") or "").strip()[:4]
                msg = next((m for m in (db_obj.get("messages") or []) if isinstance(m, dict) and int(m.get("id") or 0) == msg_id and int(m.get("post_id") or 0) == post_id), None)
                if msg and emoji:
                    reac = msg.setdefault("reactions", {})
                    lst = list(reac.get(emoji) or [])
                    if actor_id in lst:
                        lst = [x for x in lst if x != actor_id]
                    else:
                        lst.append(actor_id)
                    if lst:
                        reac[emoji] = lst
                    else:
                        reac.pop(emoji, None)
                _finish_mutation(db_obj, actor_id, is_adm)
                return
            else:
                for m in (db_obj.get("messages") or []):
                    if isinstance(m, dict) and int(m.get("post_id") or 0) == post_id and str(m.get("sender_id")) != actor_id and m.get("sender_id") != "AI_BOT":
                        m["is_read"] = 1
                _finish_mutation(db_obj, actor_id, is_adm)
                return

        if action == "submit_review":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "잘못된 모임 ID입니다."})
                return
            target_id = _resolve_uid(data.get("target_user_id"), db_obj.get("users") or {})
            if not target_id or target_id == actor_id or target_id not in (db_obj.get("users") or {}):
                self._send_json(400, {"ok": False, "message": "평가 대상을 찾을 수 없습니다."})
                return
            reviews = db_obj.setdefault("reviews", [])
            if any(isinstance(r, dict) and int(r.get("post_id") or 0) == post_id and str(r.get("from_id")) == actor_id and str(r.get("to_id")) == target_id for r in reviews):
                self._send_json(409, {"ok": False, "message": "이미 평가를 완료한 학우입니다."})
                return
            is_none = bool(data.get("is_none"))
            keyword = str(data.get("keyword") or "친절해요").strip()[:40]
            detail = str(data.get("detail") or "").strip()[:150]
            if detail and _contains_contact_info(detail):
                self._send_json(400, {"ok": False, "message": "후기에는 연락처나 SNS 아이디를 적을 수 없습니다."})
                return
            now_ms = int(time.time() * 1000)
            reviews.append({
                "id": now_ms,
                "post_id": post_id,
                "from_id": actor_id,
                "to_id": target_id,
                "keyword": "후기없음" if is_none else keyword,
                "detail": "" if is_none else detail,
                "is_none": is_none,
                "created_at": time.strftime("%Y-%m-%d"),
            })
            if not is_none:
                partner = db_obj["users"][target_id]
                actor = db_obj["users"][actor_id]
                partner["manner_temp"] = min(60.0, round(float(partner.get("manner_temp") or 36.5) + 0.5, 1))
                kws = list(partner.get("keywords") or [])
                if keyword and keyword not in kws:
                    kws.append(keyword)
                partner["keywords"] = kws
                partner["updated_at"] = now_ms
                actor["manner_temp"] = min(60.0, round(float(actor.get("manner_temp") or 36.5) + 0.2, 1))
                actor["updated_at"] = now_ms
                _add_notif(db_obj, target_id, f"{actor.get('nickname') or '학우'}님이 [{keyword}] 매너 후기를 남겨 매너온도가 0.5°C 올랐어요", post_id)
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action == "report":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            target_id = _resolve_uid(data.get("target_user_id"), db_obj.get("users") or {})
            if not target_id or target_id == actor_id:
                self._send_json(400, {"ok": False, "message": "본인 계정은 신고할 수 없습니다."})
                return
            target = (db_obj.get("users") or {}).get(target_id)
            if not isinstance(target, dict):
                self._send_json(404, {"ok": False, "message": "신고 대상을 찾을 수 없습니다."})
                return
            if _is_admin_user(target):
                self._send_json(403, {"ok": False, "message": "운영진 계정은 신고 대상에서 제외됩니다."})
                return
            rep_by = [str(x) for x in (target.get("reported_by") or [])]
            if actor_id in rep_by:
                self._send_json(409, {"ok": False, "message": "동일한 학우에게 중복 신고할 수 없어요."})
                return
            rep_by.append(actor_id)
            target["reported_by"] = rep_by
            target["report_count"] = len(rep_by)
            target["manner_temp"] = max(0.0, round(float(target.get("manner_temp") or 36.5) - 3.0, 1))
            if target["report_count"] >= 3:
                target["is_suspended"] = True
            target["updated_at"] = int(time.time() * 1000)
            _finish_mutation(db_obj, actor_id, is_adm, extra={"report_count": target["report_count"]})
            return

        if action in ("block_user", "unblock_user"):
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            target_id = _resolve_uid(data.get("target_user_id"), db_obj.get("users") or {})
            if not target_id or target_id == actor_id:
                self._send_json(400, {"ok": False, "message": "잘못된 대상입니다."})
                return
            actor = db_obj["users"][actor_id]
            bl = [str(x) for x in (actor.get("blocked_users") or [])]
            if action == "block_user":
                if _is_admin_user((db_obj.get("users") or {}).get(target_id)):
                    self._send_json(403, {"ok": False, "message": "운영진 계정은 차단할 수 없습니다."})
                    return
                if target_id not in bl:
                    bl.append(target_id)
            else:
                bl = [x for x in bl if x != target_id]
            actor["blocked_users"] = bl
            actor["updated_at"] = int(time.time() * 1000)
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action == "checkin":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            actor = db_obj["users"][actor_id]
            today = time.strftime("%Y-%m-%d")
            if actor.get("last_checkin") == today:
                self._send_json(200, {"ok": True, "already": True, "db": _sanitize_db_for_viewer(db_obj, actor_id, is_adm)})
                return
            actor["last_checkin"] = today
            actor["streak_days"] = int(actor.get("streak_days") or 0) + 1
            actor["coffee_tickets"] = int(actor.get("coffee_tickets") or 0) + 1
            actor["bonus_score"] = int(actor.get("bonus_score") or 0) + 5
            actor["updated_at"] = int(time.time() * 1000)
            _finish_mutation(db_obj, actor_id, is_adm, extra={"streak_days": actor["streak_days"], "tickets": actor["coffee_tickets"]})
            return

        if action == "spin_reward_roulette":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            actor = db_obj["users"][actor_id]
            if int(actor.get("coffee_tickets") or 0) <= 0:
                self._send_json(400, {"ok": False, "message": "보유한 룰렛 티켓이 없습니다."})
                return
            actor["coffee_tickets"] = int(actor.get("coffee_tickets") or 0) - 1
            win_idx = random.randint(0, 5)
            if win_idx == 0:
                actor["boost_coupons"] = int(actor.get("boost_coupons") or 0) + 1
            elif win_idx == 1:
                actor["extra_post_coupons"] = int(actor.get("extra_post_coupons") or 0) + 1
            elif win_idx == 2:
                actor["manner_temp"] = min(60.0, round(float(actor.get("manner_temp") or 36.5) + 0.1, 1))
            elif win_idx == 3:
                actor["coffee_tickets"] = int(actor.get("coffee_tickets") or 0) + 2
            elif win_idx == 4:
                actor["boost_coupons"] = int(actor.get("boost_coupons") or 0) + 1
                actor["bonus_score"] = int(actor.get("bonus_score") or 0) + 10
            else:
                actor["coffee_tickets"] = int(actor.get("coffee_tickets") or 0) + 1
            actor["updated_at"] = int(time.time() * 1000)
            _finish_mutation(db_obj, actor_id, is_adm, extra={"win_idx": win_idx})
            return

        if action == "update_profile":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            # 타인의 프로필 ID 수정 시도 차단
            req_target = str(data.get("target_user_id") or data.get("student_id") or "").strip()
            if req_target and req_target != actor_id and not is_adm:
                self._send_json(403, {"ok": False, "message": "본인 프로필만 수정할 수 있습니다."})
                return
            actor = db_obj["users"][actor_id]
            if "nickname" in data and str(data["nickname"]).strip():
                actor["nickname"] = str(data["nickname"]).strip()[:12]
            if "department" in data and str(data["department"]).strip():
                actor["department"] = str(data["department"]).strip()[:24]
            if "avatar" in data and str(data["avatar"]).strip():
                actor["avatar"] = str(data["avatar"]).split(" ")[0][:4]
            if "mbti" in data:
                actor["mbti"] = str(data["mbti"] or "모름/비공개").strip()[:12]
            if "bio" in data:
                actor["bio"] = str(data["bio"] or "").strip()[:80]
            if "fav_cats" in data and isinstance(data["fav_cats"], list):
                actor["fav_cats"] = [str(x)[:20] for x in data["fav_cats"][:12]]
            if "fav_muted" in data and isinstance(data["fav_muted"], list):
                actor["fav_muted"] = [str(x)[:20] for x in data["fav_muted"][:12]]
            if "timetable" in data:
                actor["timetable"] = data["timetable"] if isinstance(data["timetable"], dict) else {}
                actor["timetable_saved"] = bool(actor["timetable"])
            if "timetable_names" in data and isinstance(data["timetable_names"], dict):
                actor["timetable_names"] = {
                    str(k)[:12]: str(v or "").strip()[:60]
                    for k, v in data["timetable_names"].items()
                    if str(v or "").strip()
                }
            if "pw_hash" in data and isinstance(data["pw_hash"], str) and len(data["pw_hash"].strip()) >= 32:
                actor["pw_hash"] = data["pw_hash"].strip()
            actor["updated_at"] = int(time.time() * 1000)
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action == "mark_notifications_read":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            for n in (db_obj.get("notifications") or []):
                if isinstance(n, dict) and str(n.get("user_id")) == actor_id:
                    n["is_read"] = 1
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action in ("plaza_vote", "plaza_create_poll", "plaza_delete_poll", "plaza_create_talk", "plaza_like_talk", "plaza_reply", "plaza_delete_reply", "plaza_like_reply"):
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            now_ms = int(time.time() * 1000)
            if action == "plaza_vote":
                poll_id = data.get("poll_id")
                side = str(data.get("side") or "").upper()
                poll = next((p for p in (db_obj.get("polls") or []) if isinstance(p, dict) and str(p.get("id")) == str(poll_id)), None)
                if not poll and str(poll_id).isdigit() and 501 <= int(poll_id) <= 512:
                    meta = data.get("poll_meta") if isinstance(data.get("poll_meta"), dict) else {}
                    q_meta = str(meta.get("question") or "").strip()[:120]
                    a_meta = str(meta.get("opt_a") or "").strip()[:60]
                    b_meta = str(meta.get("opt_b") or "").strip()[:60]
                    if q_meta and a_meta and b_meta:
                        poll = {
                            "id": int(poll_id),
                            "tag": str(meta.get("tag") or "밸런스").strip()[:24],
                            "question": q_meta,
                            "opt_a": a_meta,
                            "opt_b": b_meta,
                            "votes_a": [],
                            "votes_b": [],
                            "replies": [],
                        }
                        db_obj.setdefault("polls", []).append(poll)
                if poll and side in ("A", "B"):
                    prev_voted = (actor_id in [str(u) for u in (poll.get("votes_a") or [])]) or (actor_id in [str(u) for u in (poll.get("votes_b") or [])])
                    poll["votes_a"] = [u for u in (poll.get("votes_a") or []) if str(u) != actor_id]
                    poll["votes_b"] = [u for u in (poll.get("votes_b") or []) if str(u) != actor_id]
                    poll["votes_a" if side == "A" else "votes_b"].append(actor_id)
                    if not prev_voted:
                        me_u = (db_obj.get("users") or {}).get(actor_id)
                        if isinstance(me_u, dict):
                            me_u["bonus_score"] = int(me_u.get("bonus_score") or 0) + 2
            elif action == "plaza_create_poll":
                q = str(data.get("question") or "").strip()[:100]
                a = str(data.get("opt_a") or "").strip()[:40]
                b = str(data.get("opt_b") or "").strip()[:40]
                tag = str(data.get("tag") or "밸런스").strip()[:20] or "밸런스"
                if len(q) < 3 or not a or not b:
                    self._send_json(400, {"ok": False, "message": "질문과 A, B 선택지를 모두 입력해주세요."})
                    return
                if _contains_contact_info(q) or _contains_contact_info(a) or _contains_contact_info(b) or _contains_contact_info(tag):
                    self._send_json(400, {"ok": False, "message": "외부 연락처나 SNS 아이디는 올릴 수 없어요."})
                    return
                db_obj.setdefault("polls", []).insert(0, {
                    "id": now_ms, "tag": tag, "question": q, "opt_a": a, "opt_b": b,
                    "votes_a": [], "votes_b": [], "replies": [], "author_id": actor_id,
                })
                db_obj["polls"] = db_obj["polls"][:50]
            elif action == "plaza_delete_poll":
                poll_id = data.get("poll_id")
                polls_arr = db_obj.get("polls") or []
                target = next((p for p in polls_arr if isinstance(p, dict) and str(p.get("id")) == str(poll_id)), None)
                if not target:
                    self._send_json(404, {"ok": False, "message": "삭제할 투표를 찾을 수 없어요."})
                    return
                if str(poll_id).isdigit() and 501 <= int(poll_id) <= 512 and not is_adm:
                    self._send_json(403, {"ok": False, "message": "기본 제공 밸런스 투표는 삭제할 수 없어요."})
                    return
                owner_id = str(target.get("author_id") or "")
                if owner_id != actor_id and not is_adm:
                    self._send_json(403, {"ok": False, "message": "본인이 만든 밸런스 투표만 삭제할 수 있어요."})
                    return
                db_obj["polls"] = [p for p in polls_arr if not (isinstance(p, dict) and str(p.get("id")) == str(poll_id))]
            elif action == "plaza_create_talk":
                txt = str(data.get("text") or "").strip()[:120]
                if not txt:
                    self._send_json(400, {"ok": False, "message": "내용을 입력해주세요."})
                    return
                if _contains_contact_info(txt):
                    self._send_json(400, {"ok": False, "message": "외부 연락처나 SNS 아이디는 올릴 수 없어요."})
                    return
                db_obj.setdefault("plaza_talks", []).insert(0, {
                    "id": now_ms, "created_ts": now_ms, "author_id": actor_id,
                    "text": txt, "created_at": time.strftime("%m/%d %H:%M"), "likes": [], "replies": [],
                })
                db_obj["plaza_talks"] = db_obj["plaza_talks"][:100]
            elif action == "plaza_like_talk":
                talk_id = data.get("talk_id")
                talk = next((t for t in (db_obj.get("plaza_talks") or []) if isinstance(t, dict) and str(t.get("id")) == str(talk_id)), None)
                if talk:
                    likes = [str(u) for u in (talk.get("likes") or [])]
                    if actor_id in likes:
                        likes = [u for u in likes if u != actor_id]
                    else:
                        likes.append(actor_id)
                    talk["likes"] = likes
            elif action == "plaza_reply":
                kind = str(data.get("kind") or "t")
                target_id = data.get("target_id")
                txt = str(data.get("text") or "").strip()[:200]
                if not txt or _contains_contact_info(txt):
                    self._send_json(400, {"ok": False, "message": "답글 내용을 확인해주세요. (연락처·SNS 아이디 입력 불가)"})
                    return
                arr = db_obj.setdefault("polls" if kind == "p" else "plaza_talks", [])
                item = next((x for x in arr if isinstance(x, dict) and str(x.get("id")) == str(target_id)), None)
                if not item and kind == "p" and str(target_id).isdigit() and 501 <= int(target_id) <= 512:
                    meta = data.get("poll_meta") if isinstance(data.get("poll_meta"), dict) else {}
                    q_meta = str(meta.get("question") or "").strip()[:120]
                    a_meta = str(meta.get("opt_a") or "").strip()[:60]
                    b_meta = str(meta.get("opt_b") or "").strip()[:60]
                    if q_meta and a_meta and b_meta:
                        item = {
                            "id": int(target_id),
                            "tag": str(meta.get("tag") or "밸런스").strip()[:24],
                            "question": q_meta,
                            "opt_a": a_meta,
                            "opt_b": b_meta,
                            "votes_a": [],
                            "votes_b": [],
                            "replies": [],
                        }
                        arr.append(item)
                if not item:
                    self._send_json(404, {"ok": False, "message": "대상을 찾을 수 없습니다."})
                    return
                reps = item.setdefault("replies", [])
                last_rid = max((int(r.get("id") or 0) for r in reps if isinstance(r, dict)), default=0)
                new_rid = max(now_ms, last_rid + 1)
                raw_pid = data.get("parent_id")
                parent_id = None
                if raw_pid is not None and str(raw_pid).strip() != "":
                    try:
                        pid_num = int(raw_pid)
                        if any(isinstance(r, dict) and int(r.get("id") or 0) == pid_num for r in reps):
                            parent_id = pid_num
                    except Exception:
                        parent_id = None
                new_rep = {
                    "id": new_rid,
                    "author_id": actor_id,
                    "text": txt,
                    "created_at": time.strftime("%m/%d %H:%M"),
                    "deleted": False,
                    "likes": [],
                }
                if parent_id is not None:
                    new_rep["parent_id"] = parent_id
                reps.append(new_rep)
                item["updated_at"] = now_ms
            elif action == "plaza_like_reply":
                kind = str(data.get("kind") or "t")
                target_id = data.get("target_id")
                reply_id = data.get("reply_id")
                arr = db_obj.get("polls" if kind == "p" else "plaza_talks") or []
                item = next((x for x in arr if isinstance(x, dict) and str(x.get("id")) == str(target_id)), None)
                if item:
                    for rep in (item.get("replies") or []):
                        if isinstance(rep, dict) and str(rep.get("id")) == str(reply_id):
                            likes = [str(u) for u in (rep.get("likes") or [])]
                            if actor_id in likes:
                                likes = [u for u in likes if u != actor_id]
                            else:
                                likes.append(actor_id)
                            rep["likes"] = likes
                            item["updated_at"] = now_ms
                            break
            elif action == "plaza_delete_reply":
                kind = str(data.get("kind") or "t")
                target_id = data.get("target_id")
                reply_id = data.get("reply_id")
                arr = db_obj.get("polls" if kind == "p" else "plaza_talks") or []
                item = next((x for x in arr if isinstance(x, dict) and str(x.get("id")) == str(target_id)), None)
                if item:
                    for rep in (item.get("replies") or []):
                        if isinstance(rep, dict) and str(rep.get("id")) == str(reply_id):
                            if str(rep.get("author_id")) == actor_id or is_adm:
                                rep["deleted"] = True
                            else:
                                self._send_json(403, {"ok": False, "message": "본인 답글만 삭제할 수 있습니다."})
                                return
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action == "delete_account":
            db_obj, actor_id, is_adm = _require_auth(allow_suspended=True)
            if not db_obj:
                return
            if is_adm:
                self._send_json(403, {"ok": False, "message": "운영진 계정은 삭제할 수 없습니다."})
                return
            now_ms = int(time.time() * 1000)
            db_obj.setdefault("users", {}).pop(actor_id, None)
            db_obj.setdefault("deleted_users_map", {})[actor_id] = now_ms
            user_post_ids = [
                p.get("id") for p in (db_obj.get("posts") or [])
                if isinstance(p, dict) and str(p.get("author_id")) == actor_id and p.get("id")
            ]
            db_obj["posts"] = [p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and str(p.get("author_id")) != actor_id]
            db_obj["applications"] = [a for a in (db_obj.get("applications") or []) if isinstance(a, dict) and str(a.get("applicant_id")) != actor_id and a.get("post_id") not in user_post_ids]
            db_obj["messages"] = [m for m in (db_obj.get("messages") or []) if isinstance(m, dict) and str(m.get("sender_id")) != actor_id and m.get("post_id") not in user_post_ids]
            db_obj["notifications"] = [n for n in (db_obj.get("notifications") or []) if isinstance(n, dict) and str(n.get("user_id")) != actor_id]
            db_obj["plaza_talks"] = [t for t in (db_obj.get("plaza_talks") or []) if isinstance(t, dict) and str(t.get("author_id")) != actor_id]
            if _has_supabase():
                try:
                    req_del_u = urllib.request.Request(
                        f"{SUPABASE_URL}/rest/v1/uldaemo_users?student_id=eq.{urllib.parse.quote(actor_id)}",
                        headers=_supabase_headers("return=minimal"),
                        method="DELETE",
                    )
                    with urllib.request.urlopen(req_del_u, timeout=5):
                        pass
                except Exception:
                    pass
            save_cloud_db(db_obj, user_post_ids)
            self._send_json(200, {"ok": True})
            return

        if action == "admin_dashboard_summary":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            if not is_adm:
                self._send_json(403, {"ok": False, "message": "운영진 권한(role=admin)이 필요합니다."})
                return
            users_map = db_obj.get("users") or {}
            admin_users = []
            for uid_k, u in users_map.items():
                if not isinstance(u, dict):
                    continue
                # 이메일·성별·MBTI·소개는 관리자 목록에도 포함하지 않음 (개인정보 최소화 원칙)
                admin_users.append({
                    "alias": _mask_uid(str(uid_k), actor_id),
                    "nickname": str(u.get("nickname") or "학우"),
                    "role": "admin" if _is_admin_user(u) else "user",
                    "manner_temp": float(u.get("manner_temp") if u.get("manner_temp") is not None else 36.5),
                    "report_count": int(u.get("report_count") or 0),
                    "is_suspended": bool(u.get("is_suspended")),
                    "has_pw": bool(u.get("pw_hash")),
                    "joined_at": str(u.get("joined_at") or ""),
                })
            # 신고 또는 연락처 플래그가 있는 대화방만 집계
            flagged_by_post = {}
            for m in (db_obj.get("messages") or []):
                if isinstance(m, dict) and (m.get("flagged") or _contains_contact_info(m.get("text"))):
                    pid_i = int(m.get("post_id") or 0)
                    flagged_by_post[pid_i] = flagged_by_post.get(pid_i, 0) + 1
            reported_uids = {
                str(uid_k) for uid_k, u in users_map.items()
                if isinstance(u, dict) and int(u.get("report_count") or 0) > 0
            }
            reported_rooms = []
            for p in (db_obj.get("posts") or []):
                if not isinstance(p, dict) or p.get("id") is None:
                    continue
                pid_i = int(p.get("id"))
                participants = {str(p.get("author_id") or "")}
                for a in (db_obj.get("applications") or []):
                    if isinstance(a, dict) and int(a.get("post_id") or 0) == pid_i and a.get("status") == "승인됨":
                        participants.add(str(a.get("applicant_id") or ""))
                has_rep_user = bool(participants & reported_uids)
                flg_cnt = flagged_by_post.get(pid_i, 0)
                if has_rep_user or flg_cnt > 0 or bool(p.get("reported")):
                    reported_rooms.append({
                        "post_id": pid_i,
                        "title": str(p.get("title") or ""),
                        "status": str(p.get("status") or ""),
                        "has_reported_participant": has_rep_user,
                        "flagged_message_count": flg_cnt,
                    })
            review_queue = [
                {
                    "message_id": item.get("message_id"),
                    "post_id": item.get("post_id"),
                    "flag_reason": str(item.get("flag_reason") or "contact_pattern"),
                    "flagged_at": item.get("flagged_at"),
                    "status": str(item.get("status") or "pending"),
                }
                for item in (db_obj.get("admin_review_queue") or [])
                if isinstance(item, dict)
            ]
            audit_logs = (db_obj.get("admin_audit_logs") or [])[-30:]
            self._send_json(200, {
                "ok": True,
                "users": admin_users,
                "reported_rooms": reported_rooms,
                "review_queue": review_queue,
                "audit_logs": audit_logs,
            })
            return

        if action == "admin_reported_room_messages":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            if not is_adm:
                self._send_json(403, {"ok": False, "message": "운영진 권한(role=admin)이 필요합니다."})
                return
            try:
                post_id = int(data.get("post_id"))
            except Exception:
                self._send_json(400, {"ok": False, "message": "올바른 대화방 ID를 입력해주세요."})
                return
            reason = str(data.get("reason") or "신고 검토").strip()[:100]
            post = next((p for p in (db_obj.get("posts") or []) if isinstance(p, dict) and int(p.get("id") or 0) == post_id), None)
            if not post:
                self._send_json(404, {"ok": False, "message": "대화방을 찾을 수 없습니다."})
                return
            users_map = db_obj.get("users") or {}
            participants = {str(post.get("author_id") or "")}
            for a in (db_obj.get("applications") or []):
                if isinstance(a, dict) and int(a.get("post_id") or 0) == post_id and a.get("status") == "승인됨":
                    participants.add(str(a.get("applicant_id") or ""))
            has_rep_user = any(
                isinstance(users_map.get(u), dict) and int(users_map[u].get("report_count") or 0) > 0
                for u in participants
            )
            room_msgs = [
                m for m in (db_obj.get("messages") or [])
                if isinstance(m, dict) and int(m.get("post_id") or 0) == post_id
            ]
            has_flagged = any(bool(m.get("flagged")) or _contains_contact_info(m.get("text")) for m in room_msgs)
            if not (has_rep_user or has_flagged or bool(post.get("reported"))):
                self._send_json(403, {"ok": False, "message": "신고 또는 연락처 감지 기록이 있는 대화방만 열람할 수 있습니다."})
                return
            # 접근 감사 로그 영구 기록 (메시지 본문·이메일 등 개인정보 미기록)
            now_ms = int(time.time() * 1000)
            audit_entry = {
                "id": now_ms,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "admin_alias": _mask_uid(actor_id),
                "action": "view_reported_room",
                "post_id": post_id,
                "reason": reason,
            }
            db_obj.setdefault("admin_audit_logs", []).append(audit_entry)
            db_obj["admin_audit_logs"] = db_obj["admin_audit_logs"][-200:]
            save_cloud_db(db_obj)
            sanitized_room_msgs = [
                {
                    "id": m.get("id"),
                    "post_id": post_id,
                    "sender_alias": "AI_BOT" if m.get("sender_id") == "AI_BOT" else _mask_uid(str(m.get("sender_id") or ""), actor_id),
                    "text": _strip_html_tags(m.get("text")) if m.get("sender_id") == "AI_BOT" else str(m.get("text") or ""),
                    "created_at": m.get("created_at"),
                    "flagged": bool(m.get("flagged") or _contains_contact_info(m.get("text"))),
                }
                for m in room_msgs
            ]
            self._send_json(200, {
                "ok": True,
                "post_id": post_id,
                "audit_logged": True,
                "messages": sanitized_room_msgs,
            })
            return

        if action == "admin_action":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            if not is_adm:
                self._send_json(403, {"ok": False, "message": "운영진 권한(role=admin)이 필요합니다."})
                return
            sub = str(data.get("sub_action") or "").strip()
            target_id = _resolve_uid(data.get("target_user_id"), db_obj.get("users") or {})
            target = (db_obj.get("users") or {}).get(target_id)
            now_ms = int(time.time() * 1000)
            if sub == "suspend_user" and isinstance(target, dict) and not _is_admin_user(target):
                target["is_suspended"] = True
                target["updated_at"] = now_ms
            elif sub == "unsuspend_user" and isinstance(target, dict):
                target["is_suspended"] = False
                target["report_count"] = 0
                target["reported_by"] = []
                target["updated_at"] = now_ms
            elif sub == "resolve_review_item":
                msg_id = data.get("message_id")
                for item in (db_obj.get("admin_review_queue") or []):
                    if isinstance(item, dict) and str(item.get("message_id")) == str(msg_id):
                        item["status"] = "resolved"
                        item["resolved_at"] = now_ms
            else:
                self._send_json(400, {"ok": False, "message": "지원하지 않는 관리자 동작입니다."})
                return
            db_obj.setdefault("admin_audit_logs", []).append({
                "id": now_ms,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "admin_alias": _mask_uid(actor_id),
                "action": f"admin_{sub}",
                "target_alias": _mask_uid(target_id) if target_id else "",
            })
            db_obj["admin_audit_logs"] = db_obj["admin_audit_logs"][-200:]
            _finish_mutation(db_obj, actor_id, is_adm)
            return

        if action == "ai_police":
            text = str(data.get("text", "")).strip()
            prompt = (
                "다음 메시지에 심한 욕설, 성적 발언, 또는 '카톡', '전번', '번호', '라인', '인스타' 등 "
                f"사적인 연락처를 요구하는 내용이 있다면 '경고', 평범한 대화라면 '통과'라고만 대답해. 메시지: {text}"
            )
            reply, diag = _call_gemini_text_with_diag(prompt)
            blocked = "경고" in reply
            res_body = {"ok": True, "blocked": blocked, "reply": reply}
            if not reply and diag:
                res_body["diag"] = diag[:380]
            self._send_json(200, res_body)
            return

        if action == "parse_timetable_image":
            db_obj, actor_id, is_adm = _require_auth()
            if not db_obj:
                return
            if not GEMINI_API_KEY:
                self._send_json(503, {"ok": False, "message": "AI 시간표 인식 기능이 아직 준비되지 않았어요."})
                return
            raw_img = str(data.get("image_base64") or "").strip()
            mime = str(data.get("mime_type") or "image/jpeg").strip().lower()
            if mime not in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
                mime = "image/jpeg"
            if mime == "image/jpg":
                mime = "image/jpeg"
            if "," in raw_img and raw_img.startswith("data:"):
                raw_img = raw_img.split(",", 1)[1].strip()
            if not raw_img or len(raw_img) > 4_000_000:
                self._send_json(400, {"ok": False, "message": "이미지 크기를 확인해주세요. (최대 3MB 이하)"})
                return

            tt_prompt = (
                "너는 한국 대학교 에브리타임(Everytime) 및 포털 시간표 스크린샷을 정밀 분석하는 시각 OCR 전문가야.\n"
                "첨부된 시간표 이미지의 월·화·수·목·금요일에 있는 모든 수업 블록을 찾아 JSON으로 반환해줘.\n\n"
                "[가장 중요한 규칙: 에브리타임 시간표의 세로 칸 높이(수업 시간 길이) 읽기]\n"
                "1) 왼쪽 세로축의 시간 숫자 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7은 각각 1시간짜리 가로 행(칸)을 의미하며 24시간제로 [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]시야.\n"
                "   - 특히 오후 숫자 1=13시, 2=14시, 3=15시, 4=16시, 5=17시, 6=18시, 7=19시임을 절대 헷갈리지 마!\n"
                "2) 에브리타임에서 과목 글자는 항상 색깔 블록의 맨 위쪽에만 적혀 있고, 2시간·3시간 연강 수업은 글자 아래로 색깔 박스가 가로선(격자선)을 뚫고 다음 시간 행까지 길게 이어져 있어.\n"
                "3) 따라서 절대 글자 위치만 보지 말고, 각 색깔 박스의 [맨 윗변]이 시작하는 시간(start_hour)과 [맨 아랫변]이 끝나는 시간 행(end_hour, 포함)을 반드시 가로 격자선과 대조해서 세어줘!\n"
                "   - 1시간 수업(1칸 높이): 색깔 박스가 1개 시간 행 안에서 끝남 (예: 9행에서 시작해 10행 가로선 위에서 끝남 -> start_hour: 9, end_hour: 9)\n"
                "   - 2시간 수업(2칸 높이, 1시간 30분~2시간): 색깔 박스가 가로선 1개를 넘어 다음 시간 행의 절반 이상 또는 끝까지 내려옴 (예: 9행에서 시작해 10행 아래쪽까지 내려옴 -> start_hour: 9, end_hour: 10 / 12행~1행 -> start_hour: 12, end_hour: 13 / 6행~7행 -> start_hour: 18, end_hour: 19)\n"
                "   - 3시간 수업(3칸 높이): 색깔 박스가 가로선 2개를 넘어 3개 시간 행에 걸쳐 있음 (예: 2행(14시)에서 시작해 3행(15시)을 지나 4행(16시) 아래쪽까지 내려옴 -> start_hour: 14, end_hour: 16)\n"
                "   - 주의: 색깔 박스 아랫변이 다음 행 가로선에 딱 맞춰 끝나고 다음 행 안으로 들어가지 않았으면 그 다음 행은 포함하지 마! (예: 4행(16시)에서 시작해 5행(17시) 바닥(6행 시작선)에서 끝나면 start_hour: 16, end_hour: 17)\n"
                "4) 과목명은 강의실 번호(예: 5-106, 7-613, 19호관)와 교수명만 제외하고, 줄이지 말고 전체 과목명을 그대로 적어줘.\n"
                "5) 반드시 아래 JSON 스키마만 출력해:\n"
                "{\n"
                "  \"courses\": [\n"
                "    {\"day\": \"화\", \"name\": \"인본적사고와공동체의가치\", \"start_hour\": 9, \"end_hour\": 10},\n"
                "    {\"day\": \"금\", \"name\": \"미적분학II\", \"start_hour\": 9, \"end_hour\": 9},\n"
                "    {\"day\": \"목\", \"name\": \"기초프로그래밍II\", \"start_hour\": 14, \"end_hour\": 16},\n"
                "    {\"day\": \"수\", \"name\": \"스터디\", \"start_hour\": 18, \"end_hour\": 19}\n"
                "  ]\n"
                "}\n"
                "6) 시간표가 전혀 보이지 않으면 {\"courses\": []}를 반환해."
            )
            parsed, err_detail = call_gemini_vision_json(tt_prompt, raw_img, mime)
            if not isinstance(parsed, dict):
                hint_msg = "시간표 사진을 읽지 못했어요. 글자가 잘 보이는 캡처로 다시 시도해 주세요."
                if "401" in err_detail or "403" in err_detail or "API_KEY_INVALID" in err_detail or "API key not valid" in err_detail:
                    hint_msg = "Gemini API 키 인증에 실패했어요. Vercel의 GEMINI_API_KEY 값을 다시 확인해 주세요."
                elif "429" in err_detail or "RESOURCE_EXHAUSTED" in err_detail:
                    hint_msg = "AI 요청 한도를 잠시 초과했어요. 1분 뒤 다시 시도해 주세요."
                self._send_json(502, {"ok": False, "message": hint_msg, "detail": err_detail[:180]})
                return

            valid_days = ("월", "화", "수", "목", "금")
            clean_tt = {d: [] for d in valid_days}
            clean_names = {}
            courses_list = parsed.get("courses") if isinstance(parsed.get("courses"), list) else None
            if courses_list is not None:
                day_sets = {d: set() for d in valid_days}
                for item in courses_list:
                    if not isinstance(item, dict):
                        continue
                    d = str(item.get("day") or "").strip()[:1]
                    if d not in day_sets:
                        continue
                    try:
                        sh = int(item.get("start_hour"))
                        eh = int(item.get("end_hour"))
                    except Exception:
                        continue
                    if 1 <= sh <= 7:
                        sh += 12
                    if 1 <= eh <= 7:
                        eh += 12
                    if eh < sh:
                        eh = sh
                    nm = str(item.get("name") or "").strip()[:60]
                    for h in range(max(9, sh), min(19, eh) + 1):
                        p_idx = h - 8
                        if 1 <= p_idx <= 11:
                            day_sets[d].add(p_idx)
                            if nm:
                                clean_names[f"{d}_{p_idx}"] = nm
                total_slots = 0
                for d in valid_days:
                    clean_tt[d] = sorted(day_sets[d])
                    total_slots += len(clean_tt[d])
            else:
                raw_tt = parsed.get("timetable") if isinstance(parsed.get("timetable"), dict) else {}
                raw_names = parsed.get("timetable_names") if isinstance(parsed.get("timetable_names"), dict) else {}
                total_slots = 0
                for d in valid_days:
                    arr = raw_tt.get(d) if isinstance(raw_tt.get(d), list) else []
                    periods = sorted({int(p) for p in arr if str(p).isdigit() and 1 <= int(p) <= 11})
                    clean_tt[d] = periods
                    total_slots += len(periods)
                    for p in periods:
                        k = f"{d}_{p}"
                        nm = str(raw_names.get(k) or "").strip()[:60]
                        if nm:
                            clean_names[k] = nm

            self._send_json(200, {
                "ok": True,
                "timetable": clean_tt,
                "timetable_names": clean_names,
                "count": total_slots,
            })
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
