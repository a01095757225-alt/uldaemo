import streamlit as st
import pandas as pd
import sqlite3
import os
import urllib.parse
from datetime import datetime, date, timedelta
import requests
import json

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# =========================================================
# 0. AI 헬퍼 함수 (REST API 기반 - 빠르고 안정적)
# =========================================================
def call_gemini(prompt):
    try:
        api_key = st.secrets["gemini"]["api_key"]
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        resp = requests.post(
            url,
            headers=headers,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    return ""

# =========================================================
# 1. 데이터베이스 헬퍼 함수 (클라우드 Supabase & 로컬 SQLite 호환)
# =========================================================
def is_postgres():
    if not HAS_PSYCOPG2:
        return False
    try:
        return "supabase" in st.secrets and "url" in st.secrets["supabase"]
    except Exception:
        return False

def get_connection():
    if is_postgres():
        return psycopg2.connect(st.secrets["supabase"]["url"])
    return sqlite3.connect("campus_buddy_v4.db", check_same_thread=False)

def get_dataframe(query, params=()):
    conn = get_connection()
    if is_postgres():
        query = query.replace("?", "%s")
    c = conn.cursor()
    c.execute(query, params)
    if c.description:
        columns = [desc[0] for desc in c.description]
        data = c.fetchall()
        df = pd.DataFrame(data, columns=columns)
    else:
        df = pd.DataFrame()
    conn.close()
    return df

def execute_commit(query, params=()):
    conn = get_connection()
    if is_postgres():
        query = query.replace("?", "%s")
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def notify_user(user_id, message):
    execute_commit(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (user_id, message),
    )

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    pg = is_postgres()
    id_col = "id SERIAL PRIMARY KEY" if pg else "id INTEGER PRIMARY KEY AUTOINCREMENT"

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        student_id TEXT PRIMARY KEY, email TEXT, is_verified INTEGER DEFAULT 0,
        nickname TEXT, avatar TEXT, gender TEXT, department TEXT, mbti TEXT,
        manner_temp REAL DEFAULT 36.5, report_count INTEGER DEFAULT 0
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS posts (
        {id_col}, author_id TEXT, title TEXT, category TEXT,
        meet_date TEXT, meet_time TEXT, location TEXT, max_participants INTEGER DEFAULT 1,
        meeting_style TEXT, status TEXT DEFAULT '모집중'
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS applications (
        {id_col}, post_id INTEGER, applicant_id TEXT, status TEXT DEFAULT '대기중'
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS reviews (
        {id_col}, post_id INTEGER, reviewer_id TEXT, reviewee_id TEXT,
        rating INTEGER, is_noshow INTEGER DEFAULT 0
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS keyword_reviews (
        {id_col}, post_id INTEGER, reviewer_id TEXT, reviewee_id TEXT,
        keyword TEXT
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS messages (
        {id_col}, post_id INTEGER, sender_id TEXT, text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS reports (
        {id_col}, reporter_id TEXT, reported_id TEXT, reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS notifications (
        {id_col}, user_id TEXT, message TEXT, is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def seed_demo_data_if_empty():
    """DB에 오늘 이후 활성 모집글이 하나도 없을 때 와이어프레임 시안과 동일한 예시 데이터를 초기화합니다."""
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        cnt_df = get_dataframe("SELECT count(*) as cnt FROM posts WHERE status='모집중' AND meet_date >= ?", (today_str,))
        if not cnt_df.empty and int(cnt_df.iloc[0]["cnt"]) > 0:
            return
        demo_users = [
            ("20241001", "cloud@ulsan.ac.kr", 1, "구름한점", "🐶 강아지", "남성", "컴퓨터공학과", "ENFP", 38.5, 0),
            ("20241002", "sunset@ulsan.ac.kr", 1, "노을이", "🐱 고양이", "여성", "전자공학과", "INFP", 37.2, 0),
            ("20241003", "runner@ulsan.ac.kr", 1, "민트러너", "🦊 여우", "남성", "기계공학부", "ESTP", 40.2, 0),
        ]
        for u in demo_users:
            existing = get_dataframe("SELECT student_id FROM users WHERE student_id=?", (u[0],))
            if existing.empty:
                execute_commit(
                    "INSERT INTO users (student_id, email, is_verified, nickname, avatar, gender, department, mbti, manner_temp, report_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    u,
                )
        demo_posts = [
            ("20241001", "학식 같이 먹고 다음 수업 가요!", "🍚 밥약", today_str, "23:30", "22호관 학생회관", 4, "간단한 스몰토크 환영", "모집중"),
            ("20241002", "도서관에서 두 시간 집중할 분!", "☕ 카공", today_str, "23:45", "16호관 아산도서관", 3, "이어폰 꽂고 조용히 각자 할일", "모집중"),
            ("20241003", "저녁에 운동장 가볍게 러닝하실 분!", "🏃 운동", today_str, "23:50", "39호관 아산스포츠센터", 5, "텐션 높게 E처럼 놀아요", "모집중"),
            ("20241001", "식후 캠퍼스 산책하며 커피 마셔요", "🚶 산책", today_str, "23:55", "34호관 식물원", 2, "간단한 스몰토크 환영", "모집중"),
        ]
        for p in demo_posts:
            execute_commit(
                "INSERT INTO posts (author_id, title, category, meet_date, meet_time, location, max_participants, meeting_style, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                p,
            )
        demo_kws = [
            (1, "20241002", "20241001", "시간 약속을 잘 지켜요 ⏰"),
            (1, "20241003", "20241001", "친절해요 😊"),
            (1, "20241002", "20241001", "적극적이에요 👍"),
            (2, "20241001", "20241002", "조용히 집중하기 좋아요 📚"),
        ]
        for kw in demo_kws:
            execute_commit(
                "INSERT INTO keyword_reviews (post_id, reviewer_id, reviewee_id, keyword) VALUES (?, ?, ?, ?)",
                kw,
            )
    except Exception:
        pass

init_db()
seed_demo_data_if_empty()

# =========================================================
# 2. 비즈니스 로직 헬퍼 함수
# =========================================================
def apply_rating(post_id, reviewer_id, reviewee_id, rating, keywords):
    execute_commit(
        "INSERT INTO reviews (post_id, reviewer_id, reviewee_id, rating) VALUES (?, ?, ?, ?)",
        (post_id, reviewer_id, reviewee_id, rating),
    )
    temp_change = {5: 0.5, 4: 0.2, 3: 0.0, 2: -0.5, 1: -1.0}.get(rating, 0)
    execute_commit(
        "UPDATE users SET manner_temp = manner_temp + ? WHERE student_id = ?",
        (temp_change, reviewee_id),
    )
    for kw in keywords:
        execute_commit(
            "INSERT INTO keyword_reviews (post_id, reviewer_id, reviewee_id, keyword) VALUES (?, ?, ?, ?)",
            (post_id, reviewer_id, reviewee_id, kw),
        )

def apply_noshow(post_id, reporter_id, reported_id):
    execute_commit(
        "INSERT INTO reviews (post_id, reviewer_id, reviewee_id, rating, is_noshow) VALUES (?, ?, ?, 1, 1)",
        (post_id, reporter_id, reported_id),
    )
    execute_commit(
        "INSERT INTO reports (reporter_id, reported_id, reason) VALUES (?, ?, '노쇼')",
        (reporter_id, reported_id),
    )
    execute_commit(
        "UPDATE users SET manner_temp = manner_temp - 5.0, report_count = report_count + 1 WHERE student_id = ?",
        (reported_id,),
    )

# =========================================================
# 3. 디자인 토큰 및 재사용 UI 컴포넌트 (Section 5 & 7 명세)
# =========================================================
CATEGORY_META = {
    "전체": {"icon": "🟢", "bg": "#287D62", "fg": "#FFFFFF", "chip_bg": "#DDF2E7", "chip_fg": "#287D62"},
    "밥약": {"icon": "🍚", "bg": "#FFF3E0", "fg": "#E65100", "chip_bg": "#FFF3E0", "chip_fg": "#E65100"},
    "카공": {"icon": "💻", "bg": "#E8EAF6", "fg": "#283593", "chip_bg": "#E8EAF6", "chip_fg": "#283593"},
    "운동": {"icon": "🏃", "bg": "#E0F2F1", "fg": "#00695C", "chip_bg": "#E0F2F1", "chip_fg": "#00695C"},
    "산책": {"icon": "🚶", "bg": "#E8F5E9", "fg": "#2E7D32", "chip_bg": "#E8F5E9", "chip_fg": "#2E7D32"},
    "기타": {"icon": "✨", "bg": "#F3E5F5", "fg": "#6A1B9A", "chip_bg": "#F3E5F5", "chip_fg": "#6A1B9A"},
}

def normalize_category(raw_cat):
    if not raw_cat:
        return "기타"
    if "밥약" in raw_cat or "식사" in raw_cat or "학식" in raw_cat or "맛집" in raw_cat:
        return "밥약"
    if "카공" in raw_cat or "스터디" in raw_cat or "공부" in raw_cat or "도서관" in raw_cat:
        return "카공"
    if "운동" in raw_cat or "축구" in raw_cat or "러닝" in raw_cat or "헬스" in raw_cat or "농구" in raw_cat or "배드민턴" in raw_cat:
        return "운동"
    if "산책" in raw_cat:
        return "산책"
    return "기타"

def format_category_badge(raw_cat):
    norm_cat = normalize_category(raw_cat)
    meta = CATEGORY_META.get(norm_cat, CATEGORY_META["기타"])
    raw_str = str(raw_cat).strip() if raw_cat else "기타"
    if norm_cat in ("밥약", "카공", "운동", "산책") and (raw_str in ("🍚 밥약", "☕ 카공", "💻 카공", "🏃 운동", "🚶 산책", "밥약", "카공", "운동", "산책")):
        return f"{meta['icon']} {norm_cat}", meta
    # 직접 입력하거나 세부 활동을 선택한 경우 사용자가 입력한 텍스트를 그대로 배지에 표시
    if raw_str and not raw_str[0].isalnum():
        return raw_str, meta
    return f"{meta['icon']} {raw_str}", meta

def inject_design_tokens():
    st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

    :root {
        --primary: #287D62;
        --primary-dark: #1E634C;
        --secondary: #DDF2E7;
        --bg: #F7F8F4;
        --surface: #FFFFFF;
        --text-main: #191F28;
        --text-sub: #6B7684;
        --border: #E5E8EB;
        --radius-card: 16px;
        --radius-btn: 12px;
    }

    html, body, .stApp, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
        color: var(--text-main);
        background-color: var(--bg);
        overflow-x: hidden !important;
    }

    /* 모바일 기준 프레임 (390~440px 중심 반응형 컨테이너) */
    .main .block-container {
        max-width: 440px !important;
        width: 100% !important;
        box-sizing: border-box !important;
        padding-top: 1rem !important;
        padding-bottom: 5rem !important;
        padding-left: 16px !important;
        padding-right: 16px !important;
        margin: 0 auto !important;
    }

    @media (max-width: 640px) {
        .main .block-container {
            padding-left: 12px !important;
            padding-right: 12px !important;
        }
        div[data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 6px !important;
        }
        div[data-testid="stColumn"] {
            width: auto !important;
            flex: 1 1 0% !important;
            min-width: 0 !important;
        }
        div.stButton > button {
            padding: 4px 6px !important;
            font-size: 12.5px !important;
            min-height: 42px !important;
        }
    }

    /* 상단 헤더 (AppHeader) */
    .app-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0 14px 0;
    }
    .app-logo-wrap {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .app-logo-title {
        font-size: 22px;
        font-weight: 800;
        color: #287D62;
        letter-spacing: -0.5px;
    }
    .campus-pill {
        background: #FFFFFF;
        border: 1px solid #D1D6DB;
        padding: 5px 12px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        color: #191F28;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    /* 메인 배너 (MainBanner) */
    .main-banner {
        background: linear-gradient(135deg, #DDF2E7 0%, #EBF8F1 100%);
        border: 1px solid #C5E6D6;
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        position: relative;
        overflow: hidden;
    }
    .main-banner-tag {
        color: #287D62;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .main-banner-title {
        color: #191F28;
        font-size: 19px;
        font-weight: 800;
        line-height: 1.35;
        margin: 0;
    }

    /* 공통 카드 (MeetupCard / Detail Card) */
    .uldaemo-card {
        background: #FFFFFF;
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 12px;
        border: 1px solid #E5E8EB;
        box-shadow: 0 2px 10px rgba(25, 31, 40, 0.04);
    }

    /* 익명 보호 배지 (PrivacyBadge) */
    .privacy-badge {
        background: #EEF8F3;
        color: #287D62;
        border: 1px solid #C5E6D6;
        padding: 8px 12px;
        border-radius: 10px;
        font-size: 12px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 6px;
        margin: 8px 0;
    }
    .privacy-pill-mini {
        background: #EEF8F3;
        color: #287D62;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 700;
    }

    /* 매너 온도 게이지 (MannerTemperature) */
    .temp-wrap {
        width: 100%;
        margin: 4px 0;
    }
    .temp-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 12px;
        font-weight: 700;
        color: #287D62;
        margin-bottom: 4px;
    }
    .temp-track {
        width: 100%;
        height: 7px;
        background: #E5E8EB;
        border-radius: 999px;
        overflow: hidden;
    }
    .temp-fill {
        height: 100%;
        background: linear-gradient(90deg, #48BB78 0%, #287D62 100%);
        border-radius: 999px;
    }

    /* 칭찬 키워드 스티커 (PraiseTag) */
    .praise-tag {
        display: inline-block;
        background: #EEF8F3;
        color: #287D62;
        border: 1px solid #C5E6D6;
        font-size: 11px;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 999px;
        margin-right: 6px;
        margin-bottom: 6px;
    }

    /* 카카오맵 버튼 (KakaoMapButton) */
    .kakaomap-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        background: #FFFFFF;
        color: #191F28 !important;
        border: 1px solid #D1D6DB;
        padding: 7px 14px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        text-decoration: none !important;
        transition: all 0.15s ease;
    }
    .kakaomap-link:hover {
        background: #DDF2E7;
        border-color: #287D62;
        color: #287D62 !important;
    }

    /* 채팅 말풍선 (ChatMessage) */
    .chat-bubble-me {
        background: #287D62;
        color: #FFFFFF;
        padding: 10px 14px;
        border-radius: 16px 16px 4px 16px;
        max-width: 78%;
        margin-left: auto;
        margin-bottom: 8px;
        font-size: 13.5px;
        line-height: 1.45;
        word-break: break-word;
    }
    .chat-bubble-other {
        background: #FFFFFF;
        color: #191F28;
        border: 1px solid #E5E8EB;
        padding: 10px 14px;
        border-radius: 16px 16px 16px 4px;
        max-width: 78%;
        margin-right: auto;
        margin-bottom: 8px;
        font-size: 13.5px;
        line-height: 1.45;
        word-break: break-word;
    }
    .chat-bubble-ai {
        background: #EEF8F3;
        color: #1E634C;
        border: 1px solid #C5E6D6;
        padding: 10px 14px;
        border-radius: 12px;
        margin: 8px 0;
        font-size: 13px;
        line-height: 1.45;
    }

    /* 버튼 및 컨테이너 오버라이드 (높이 약 44~48px, 라운딩 12px) */
    div.stButton > button {
        border-radius: 12px !important;
        min-height: 44px !important;
        font-weight: 700 !important;
        font-size: 14px !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 16px !important;
        background-color: #FFFFFF !important;
        border: 1px solid #E5E8EB !important;
        box-shadow: 0 2px 8px rgba(25, 31, 40, 0.04) !important;
        padding: 14px !important;
        margin-bottom: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)

def render_uldaemo_logo_svg(size=32):
    return f'<svg width="{size}" height="{size}" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="40" height="40" rx="12" fill="#287D62"/><circle cx="14.5" cy="14.5" r="3" fill="#DDF2E7"/><circle cx="25.5" cy="14.5" r="3" fill="#DDF2E7"/><path d="M12 22.5C13.8 26.5 16.8 28.5 20 28.5C23.2 28.5 26.2 26.5 28 22.5" stroke="#FFFFFF" stroke-width="3.2" stroke-linecap="round"/></svg>'

def AppHeader(unread_cnt=0):
    notif_badge = f"🔔 {unread_cnt}" if unread_cnt > 0 else "🔔 알림"
    notif_style = "background:#EEF8F3; color:#287D62; border-color:#287D62;" if unread_cnt > 0 else ""
    st.markdown(
        f'<div class="app-header"><div class="app-logo-wrap">{render_uldaemo_logo_svg(32)}<div><div class="app-logo-title">울대모</div><div style="font-size:11px; color:#6B7684; font-weight:600; margin-top:-3px;">우리 학교, 가볍게 모여!</div></div></div><div style="display:flex; align-items:center; gap:6px;"><span class="campus-pill">📍 울산대학교 ▾</span><span class="campus-pill" style="{notif_style}">{notif_badge}</span></div></div>',
        unsafe_allow_html=True,
    )

def MainBanner():
    st.markdown(
        '<div class="main-banner"><div style="z-index:2;"><div class="main-banner-tag">오늘도 좋은 하루예요! 🌱</div><p class="main-banner-title">공강 시간,<br>같이 보낼 학우를<br>찾아봐요!</p></div><svg width="96" height="84" viewBox="0 0 96 84" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="52" cy="44" r="36" fill="#C5E6D6" fill-opacity="0.6"/><rect x="28" y="34" width="48" height="36" rx="4" fill="#FFFFFF" stroke="#287D62" stroke-width="2"/><path d="M22 36L52 16L82 36" stroke="#287D62" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><rect x="46" y="48" width="12" height="22" rx="2" fill="#287D62"/><circle cx="52" cy="29" r="4" fill="#287D62"/></svg></div>',
        unsafe_allow_html=True,
    )
    if st.button("➕ 번개 모집하기", key="hero_create_btn", use_container_width=True, type="primary"):
        st.session_state.active_modal = "create"
        st.rerun()

def MannerTemperature(temp_val, show_label=True):
    pct = max(5, min(100, int((float(temp_val) / 60.0) * 100)))
    badge = "✅" if float(temp_val) >= 40.0 else ""
    label_html = "<span>매너 온도</span>" if show_label else "<span></span>"
    return f'<div class="temp-wrap"><div class="temp-header">{label_html}<span>🌡️ {float(temp_val):.1f}°C {badge}</span></div><div class="temp-track"><div class="temp-fill" style="width: {pct}%;"></div></div></div>'

# 하위 호환성 유지
def render_temp_gauge(temp_val):
    return MannerTemperature(temp_val, show_label=True)

def PraiseTag(keywords):
    if not keywords:
        return ""
    tags = "".join([f'<span class="praise-tag">{kw}</span>' for kw in keywords])
    return f"<div style='margin-top:6px;'>{tags}</div>"

def PrivacyBadge(text="방장 수락 전까지 익명 보장됩니다."):
    return f'<div class="privacy-badge"><span>🛡️</span><span>{text}</span></div>'

# 울산대학교 공식 캠퍼스맵(ulsan.ac.kr) 기준 전 건물(1호관~46호관, S01호관) 및 주요 학내·외 장소 실제 GPS 좌표
ULSAN_CAMPUS_COORDS = {
    "1호관 화학공학관": (35.544734, 129.255810, "💻"),
    "2호관 기계항공관": (35.545027, 129.255057, "💻"),
    "3호관 공학행정관": (35.545173, 129.255690, "📍"),
    "4호관 학생회관별관": (35.544460, 129.254443, "📍"),
    "5호관 산학협력리더스홀": (35.544032, 129.254522, "💻"),
    "6호관 조형관": (35.543474, 129.254744, "🎨"),
    "7호관 전기/컴퓨터공학관": (35.544225, 129.255796, "💻"),
    "8호관 자연과학관": (35.542938, 129.256658, "💻"),
    "9호관 대학회관/해송홀": (35.544825, 129.256463, "🍚"),
    "10호관 문수관": (35.543568, 129.255507, "💻"),
    "11호관 교수연구동": (35.543055, 129.255730, "☕"),
    "12호관 체육관": (35.545279, 129.258179, "🏃"),
    "13호관 동아리관1": (35.544010, 129.258601, "🎸"),
    "14호관 인문관": (35.542500, 129.257440, "💻"),
    "15호관 사회과학관": (35.542045, 129.257664, "💻"),
    "16호관 아산도서관": (35.543219, 129.258113, "📚"),
    "18호관 재료/산업공학관": (35.544748, 129.253859, "💻"),
    "19호관 기초과학실험동": (35.544138, 129.253935, "💻"),
    "20호관 시청각교육관": (35.541422, 129.256770, "💻"),
    "21호관 학군단": (35.543908, 129.259001, "📍"),
    "22호관 학생회관": (35.544589, 129.258501, "🍚"),
    "23호관 건설환경공학관": (35.545616, 129.254878, "💻"),
    "24호관 경영관": (35.542247, 129.256487, "💻"),
    "25호관 청운학사 무거관": (35.547148, 129.255825, "🏠"),
    "26호관 행정본관": (35.543723, 129.257063, "📍"),
    "27호관 해양공학수조": (35.544654, 129.252139, "💻"),
    "28호관 예술관(디자인학부/미술학부)": (35.543079, 129.254168, "🎨"),
    "29호관 예술관(음악학부)": (35.543553, 129.254159, "🎵"),
    "30호관 공장실험동": (35.545448, 129.253854, "💻"),
    "31호관 동아리관2": (35.543874, 129.259234, "🎸"),
    "32호관 조소실습동": (35.544959, 129.250475, "🎨"),
    "34호관 식물원": (35.541588, 129.257191, "🚶"),
    "35호관 산학협동관/의학관": (35.544954, 129.252952, "💻"),
    "36호관 서점 및 북카페": (35.544643, 129.258260, "☕"),
    "37호관 생활과학관": (35.542550, 129.255253, "💻"),
    "38호관 청운학사 목련관": (35.547437, 129.255933, "🏠"),
    "39호관 아산스포츠센터": (35.544198, 129.259535, "🏃"),
    "40호관 아산도서관 신관": (35.542539, 129.258585, "📚"),
    "41호관 조선해양공학관": (35.545009, 129.251824, "💻"),
    "42호관 조선해양공학시험동": (35.545141, 129.251227, "💻"),
    "43호관 국제관": (35.546591, 129.255746, "🌐"),
    "44호관 건축관": (35.546126, 129.256497, "💻"),
    "45호관 청운학사 기린관": (35.546804, 129.257144, "🏠"),
    "46호관 KCC 생활관": (35.546200, 129.257849, "🏠"),
    "S01호관 미래융합관": (35.511946, 129.297409, "💻"),
    "학생식당 (9호관 대학회관 1층)": (35.544639, 129.257122, "🍚"),
    "11호관 커피숍 (교수연구동 1층)": (35.542999, 129.255789, "☕"),
    "이마트24 1호점 (9호관 대학회관)": (35.544621, 129.257036, "🏪"),
    "이마트24 2호점 (2호관 기계항공관 옆)": (35.545179, 129.254858, "🏪"),
    "이마트24 3호점 (40호관 도서관 신관)": (35.542439, 129.258265, "🏪"),
    "중앙잔디 (본관·문수관 사이)": (35.543630, 129.256264, "🚶"),
    "야외식물원 (34호관 뒤)": (35.541166, 129.257204, "🚶"),
    "종합운동장 (대운동장·축구장)": (35.545736, 129.259553, "🏃"),
    "풋살축구장 (12호관 체육관 옆)": (35.545652, 129.260411, "🏃"),
    "농구장 (45호관 기린관 옆)": (35.547271, 129.256498, "🏀"),
    "농구장2 (12호관 체육관 옆)": (35.546267, 129.258852, "🏀"),
    "족구장 (12호관 체육관 옆)": (35.545892, 129.258665, "🏃"),
    "학생테니스코트 (12호관 맞은편)": (35.545152, 129.257067, "🎾"),
    "야외헬스장 (45호관 기린관 앞)": (35.546674, 129.256581, "🏃"),
    "울산전파천문대 (42호관 위)": (35.545873, 129.250048, "🔭"),
    "정문 앞": (35.543250, 129.259820, "📍"),
    "바보사거리 앞": (35.543131, 129.260650, "🍚"),
}

@st.cache_data(ttl=3600, show_spinner=False)
def geocode_custom_location(loc_str):
    import urllib.request
    for prefix in ["울산 남구 무거동 ", "울산대학교 ", "울산 "]:
        try:
            q = urllib.parse.quote(prefix + loc_str)
            url = f"https://nominatim.openstreetmap.org/search?format=json&limit=1&q={q}"
            req = urllib.request.Request(url, headers={"User-Agent": "UldaemoCampusApp/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            continue
    return None

def resolve_campus_location(loc_name):
    loc_str = str(loc_name).strip()
    if loc_str in ULSAN_CAMPUS_COORDS:
        return ULSAN_CAMPUS_COORDS[loc_str]
    for b_name, b_val in ULSAN_CAMPUS_COORDS.items():
        short_b = b_name.split("호관 ", 1)[1] if "호관 " in b_name else b_name
        short_clean = short_b.split(" (")[0].strip()
        if b_name in loc_str or loc_str in b_name or (short_clean and short_clean in loc_str):
            return b_val
    # 목록에 없는 '직접 입력' 장소일 경우 실시간 주소/상호명 좌표 검색(Geocoding) 수행
    geocoded = geocode_custom_location(loc_str)
    if geocoded:
        return (geocoded[0], geocoded[1], "📍")
    return (35.543723, 129.257063, "🟢")

def KakaoMapButton(location_name, label="📍 카카오맵으로 보기"):
    search_loc = location_name
    if "호관 " in search_loc:
        search_loc = search_loc.split("호관 ", 1)[1]
    map_query = urllib.parse.quote(f"울산대학교 {search_loc}")
    url = f"https://map.kakao.com/link/search/{map_query}"
    return f'<a class="kakaomap-link" href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'

def EmptyState(title="현재 모집 중인 번개가 없어요", subtitle="첫 번째 번개 모임을 가볍게 열어보세요!"):
    st.markdown(f"""
    <div class="uldaemo-card" style="text-align:center; padding:32px 16px;">
        <div style="font-size:36px; margin-bottom:8px;">🌱</div>
        <div style="font-size:16px; font-weight:800; color:#191F28; margin-bottom:4px;">{title}</div>
        <div style="font-size:13px; color:#6B7684;">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

def CategoryFilter(state_key="selected_cat"):
    if state_key not in st.session_state:
        st.session_state[state_key] = "전체"
    cats = ["전체", "밥약", "카공", "운동", "산책"]
    cols = st.columns(5)
    for idx, c_name in enumerate(cats):
        meta = CATEGORY_META[c_name]
        is_active = st.session_state[state_key] == c_name
        btn_label = f"{meta['icon']}\n{c_name}"
        if cols[idx].button(
            btn_label,
            key=f"{state_key}_btn_{c_name}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state[state_key] = c_name
            st.rerun()
    return st.session_state[state_key]

def get_user_top_keywords(student_id, limit=2):
    kws_df = get_dataframe(
        "SELECT keyword, count(*) as cnt FROM keyword_reviews WHERE reviewee_id=? GROUP BY keyword ORDER BY cnt DESC LIMIT ?",
        (student_id, limit),
    )
    if kws_df.empty:
        return ["약속을 잘 지켜요", "친절해요"]
    return [str(r["keyword"]).split()[0] + " " + (str(r["keyword"]).split()[1] if len(str(r["keyword"]).split()) > 1 else "") for _, r in kws_df.iterrows()]

def calc_campus_distance_meters(lat1, lng1, lat2, lng2):
    import math
    r_earth = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * (math.sin(dl / 2.0) ** 2)
    return int(round(r_earth * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))))

def MeetupCard(row, accepted_cnt, my_app_status, key_prefix="feed", distance_m=None):
    badge_label, meta = format_category_badge(row["category"])
    dept_str = row["department"] if "department" in row and pd.notna(row["department"]) else "컴퓨터공학과"
    is_mine = str(row["author_id"]) == str(st.session_state.user_id)
    is_full = int(accepted_cnt) >= int(row["max_participants"])
    top_kws = get_user_top_keywords(row["author_id"], limit=2)

    dist_badge_html = ""
    if distance_m is not None:
        if distance_m < 25:
            dist_str = "📍 현재 계신 장소 바로 근처"
        else:
            walk_min = max(1, int(round(distance_m / 67.0)))
            dist_str = f"🚶 내 위치에서 약 {distance_m}m (도보 {walk_min}분)"
        dist_badge_html = f'<span style="background:#E8F3FF; color:#1B64DA; font-size:11.5px; font-weight:800; padding:3px 9px; border-radius:999px;">{dist_str}</span>'

    privacy_pill_html = "<span class='privacy-pill-mini'>⭐ 내 모집글</span>" if is_mine else "<span class='privacy-pill-mini'>🔒 익명 보장</span>"

    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; flex-wrap:wrap; gap:4px;">'
            f'<div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">'
            f'<span style="background:{meta["chip_bg"]}; color:{meta["chip_fg"]}; font-size:12px; font-weight:800; padding:3px 10px; border-radius:999px;">{badge_label}</span>'
            f'{privacy_pill_html}{dist_badge_html}'
            f'</div>'
            f'<span style="font-size:11px; color:#8B95A1; font-weight:600;">{row["meeting_style"]}</span>'
            f'</div>'
            f'<div style="font-size:17px; font-weight:800; color:#191F28; margin-bottom:6px; line-height:1.35;">{row["title"]}</div>'
            f'<div style="font-size:12.5px; color:#4E5968; display:flex; flex-wrap:wrap; gap:10px; margin-bottom:10px;">'
            f'<span>📍 <b>{row["location"]}</b></span>'
            f'<span>🕒 <b>{row["meet_date"]} {row["meet_time"]}</b></span>'
            f'<span>👥 <b>{accepted_cnt} / {row["max_participants"]}명</b></span>'
            f'</div>'
            f'<div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #F2F4F6; padding-top:10px; margin-bottom:4px;">'
            f'<div>'
            f'<div style="font-size:13.5px; font-weight:700; color:#191F28;">{row["avatar"]} {row["nickname"]} {"✅" if float(row["manner_temp"]) >= 40.0 else ""}</div>'
            f'<div style="font-size:11.5px; color:#6B7684;">{dept_str} · {row["mbti"]}</div>'
            f'</div>'
            f'<div style="width:135px;">{MannerTemperature(row["manner_temp"], show_label=False)}</div>'
            f'</div>'
            f'{PraiseTag(top_kws)}',
            unsafe_allow_html=True,
        )

        b_col1, b_col2 = st.columns([1, 1.3])
        with b_col1:
            if st.button("상세 보기", key=f"{key_prefix}_detail_{row['id']}", use_container_width=True):
                st.session_state.selected_post_id = int(row["id"])
                st.session_state.active_modal = "detail"
                st.rerun()
        with b_col2:
            if is_mine:
                if st.button("신청자 관리", key=f"{key_prefix}_manage_{row['id']}", use_container_width=True):
                    st.session_state.selected_post_id = int(row["id"])
                    st.session_state.active_modal = "detail"
                    st.rerun()
            elif my_app_status == "승인됨":
                if st.button("💬 안심 채팅 이동", key=f"{key_prefix}_chat_{row['id']}", use_container_width=True, type="primary"):
                    st.session_state.nav_tab = "채팅"
                    st.session_state.active_modal = None
                    st.rerun()
            elif my_app_status == "대기중":
                st.button("⏳ 수락 대기중", key=f"{key_prefix}_wait_{row['id']}", use_container_width=True, disabled=True)
            elif is_full:
                st.button("모집 마감", key=f"{key_prefix}_full_{row['id']}", use_container_width=True, disabled=True)
            else:
                if st.button("참여 신청", key=f"{key_prefix}_apply_{row['id']}", use_container_width=True, type="primary"):
                    check = get_dataframe(
                        "SELECT * FROM applications WHERE post_id=? AND applicant_id=?",
                        (row["id"], st.session_state.user_id),
                    )
                    if check.empty:
                        execute_commit(
                            "INSERT INTO applications (post_id, applicant_id, status) VALUES (?, ?, '대기중')",
                            (row["id"], st.session_state.user_id),
                        )
                        notify_user(row["author_id"], f"[{row['title']}] 모임에 새로운 참여 신청이 도착했습니다!")
                        st.toast("참여 신청 완료! 방장이 수락하면 안심 채팅이 열립니다.")
                        st.rerun()

def render_chat(post_id, my_id, other_id, other_name, unique_suffix, post_meta=None):
    """안심 채팅 컴포넌트 (SafeChat & ChatMessage)"""
    if post_meta is None:
        p_df = get_dataframe("SELECT title, meet_date, meet_time, location, max_participants FROM posts WHERE id=?", (post_id,))
        post_meta = p_df.iloc[0].to_dict() if not p_df.empty else {"title": "캠퍼스 번개", "meet_date": "", "meet_time": "", "location": "울산대학교", "max_participants": 2}

    st.markdown(f"""
    <div class="uldaemo-card" style="padding:14px 16px; background:#EEF8F3; border-color:#C5E6D6; margin-bottom:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="font-size:15px; font-weight:800; color:#191F28;">💬 {other_name}</span>
                <span style="font-size:11px; color:#287D62; font-weight:700; margin-left:6px;">● 온라인</span>
            </div>
            <span class="privacy-pill-mini">🛡️ 안심 채팅방</span>
        </div>
        <div style="font-size:12px; color:#287D62; margin-top:4px; font-weight:600;">
            방장이 수락하여 열린 안전한 채팅방입니다. 외부 연락처 요구는 AI가 실시간 차단합니다.
        </div>
        <div style="background:#FFFFFF; border-radius:10px; padding:8px 12px; margin-top:8px; font-size:12px; color:#4E5968; display:flex; justify-content:space-between; align-items:center;">
            <span>📌 <b>{post_meta.get('title', '')}</b> · {post_meta.get('meet_time', '')} · {post_meta.get('location', '')}</span>
            {KakaoMapButton(post_meta.get('location', '울산대학교'), '지도')}
        </div>
    </div>
    """, unsafe_allow_html=True)

    msgs = get_dataframe(
        "SELECT sender_id, text, created_at FROM messages WHERE post_id=? ORDER BY id ASC",
        (post_id,),
    )

    # 새 메시지 알림음
    chat_key = f"chat_count_{post_id}_{other_id}_{unique_suffix}"
    current_len = len(msgs)
    if chat_key not in st.session_state:
        st.session_state[chat_key] = current_len
    if current_len > st.session_state[chat_key]:
        last_msg = msgs.iloc[-1]
        if str(last_msg["sender_id"]) != str(my_id):
            st.components.v1.html("""
                <audio autoplay>
                    <source src="https://actions.google.com/sounds/v1/alarms/beep_short.ogg" type="audio/ogg">
                </audio>
            """, height=0)
        st.session_state[chat_key] = current_len

    chat_box = st.container(height=280)
    with chat_box:
        st.markdown(
            "<div style='text-align:center; font-size:11.5px; color:#8B95A1; margin-bottom:10px;'>방장이 참여 신청을 수락했습니다. 이제 안전한 채팅을 이용할 수 있어요.</div>",
            unsafe_allow_html=True,
        )
        if msgs.empty:
            st.markdown(
                "<div style='text-align:center; font-size:12.5px; color:#6B7684; padding:30px 0;'>첫 인사를 건네거나 🤖 AI 아이스브레이커를 눌러보세요!</div>",
                unsafe_allow_html=True,
            )
        for _, msg in msgs.iterrows():
            sender = str(msg["sender_id"])
            txt = str(msg["text"])
            if sender == str(my_id):
                st.markdown(f'<div class="chat-bubble-me">{txt}</div>', unsafe_allow_html=True)
            elif sender == "AI_BOT":
                st.markdown(f'<div class="chat-bubble-ai">{txt}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-bubble-other"><b>{other_name}</b><br>{txt}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([4.2, 1.2])
    new_msg = col1.text_input(
        "메시지 입력",
        key=f"msg_input_{post_id}_{other_id}_{unique_suffix}",
        placeholder="메시지를 입력하세요...",
        label_visibility="collapsed",
    )
    if col2.button("전송", key=f"send_btn_{post_id}_{other_id}_{unique_suffix}", use_container_width=True, type="primary"):
        if new_msg.strip():
            # 로컬 빠른 필터 (정규식 기반 전화번호/이메일/SNS 아이디 차단) + Gemini AI 경찰 이중 보호
            import re
            banned_tokens = ["카톡", "카카오톡", "톡디", "전번", "전화번호", "010-", "오픈채팅", "인스타", "kakao", "ktalk", "insta"]
            phone_pattern = re.compile(r"01[016789][\s\-]?\d{3,4}[\s\-]?\d{4}")
            email_pattern = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
            msg_lower = new_msg.lower()
            if (
                any(tok in msg_lower for tok in banned_tokens)
                or phone_pattern.search(new_msg)
                or email_pattern.search(new_msg)
            ):
                st.error("🚨 [안심 AI 경찰] 사적인 외부 연락처(카톡, 전화번호, 이메일 등) 공유가 감지되어 전송이 차단되었습니다.")
                st.stop()
            with st.spinner("경찰 AI가 메시지를 검사 중입니다... 🚓"):
                prompt = f"다음 메시지에 심한 욕설, 성적 발언, 또는 '카톡', '전번', '번호', '라인', '인스타' 등 사적인 연락처를 요구하는 내용이 있다면 '경고', 평범한 대화라면 '통과'라고만 대답해. 메시지: {new_msg}"
                resp = call_gemini(prompt).strip()
                if "경고" in resp:
                    st.error("🚨 [안심 AI 경찰] 부적절한 언행 또는 외부 연락처 요구가 감지되어 메시지 전송이 차단되었습니다.")
                    st.stop()
            execute_commit(
                "INSERT INTO messages (post_id, sender_id, text) VALUES (?, ?, ?)",
                (post_id, my_id, new_msg.strip()),
            )
            st.rerun()

    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        if st.button("🔄 새로고침", key=f"refresh_{post_id}_{other_id}_{unique_suffix}", use_container_width=True):
            st.rerun()
    with ac2:
        if st.button("🤖 AI 주제추천", key=f"ai_btn_{post_id}_{other_id}_{unique_suffix}", use_container_width=True):
            with st.spinner("AI 아이스브레이커 작성 중... 💡"):
                post_info = get_dataframe("SELECT category, location, meeting_style FROM posts WHERE id=?", (post_id,)).iloc[0]
                prompt = f"대학생 두 명이 현재 '{post_info['location']}'에서 '{post_info['category']}' 목적으로 만나는 중이야. 둘의 만남 성향은 '{post_info['meeting_style']}'이야. 어색함을 깰 수 있는 재미있는 대화 소재 1가지와, 근처 맛집이나 놀거리 1가지를 3줄로 발랄하게 추천해줘."
                ai_reply = call_gemini(prompt)
                if not ai_reply:
                    ai_reply = f"💡 **{post_info['location']}** 근처에서 만나는군요! 오늘 수업이나 공강 루틴 이야기로 가볍게 대화를 시작해 보세요. 모임 후 근처 학생식당이나 북카페 코스를 추천해요!"
                execute_commit(
                    "INSERT INTO messages (post_id, sender_id, text) VALUES (?, ?, ?)",
                    (post_id, "AI_BOT", f"🤖 <b>[AI 아이스브레이커]</b><br>{ai_reply}"),
                )
                st.rerun()
    with ac3:
        if st.button("🚨 신고/차단", key=f"report_toggle_{post_id}_{other_id}_{unique_suffix}", use_container_width=True):
            st.session_state[f"show_report_{post_id}_{unique_suffix}"] = not st.session_state.get(f"show_report_{post_id}_{unique_suffix}", False)

    if st.session_state.get(f"show_report_{post_id}_{unique_suffix}", False):
        with st.container(border=True):
            st.markdown("**🚨 안심 신고 및 차단 센터**")
            reason = st.selectbox(
                "신고 사유 선택",
                ["외부 연락처(카톡/전화번호) 지속 요구", "불쾌한 언행 또는 비매너 채팅", "노쇼(약속 장소 불참) 신고"],
                key=f"reason_{post_id}_{unique_suffix}",
            )
            if st.button("신고 접수 및 차단하기", key=f"confirm_report_{post_id}_{unique_suffix}", type="primary"):
                if "노쇼" in reason:
                    apply_noshow(post_id, my_id, other_id)
                else:
                    execute_commit(
                        "INSERT INTO reports (reporter_id, reported_id, reason) VALUES (?, ?, ?)",
                        (my_id, other_id, reason),
                    )
                    execute_commit(
                        "UPDATE users SET manner_temp = manner_temp - 3.0, report_count = report_count + 1 WHERE student_id = ?",
                        (other_id,),
                    )
                st.success("신고가 접수되어 상대방의 매너 온도 차감 및 보호 조치가 적용되었습니다.")
                st.session_state[f"show_report_{post_id}_{unique_suffix}"] = False
                st.rerun()

def render_sidebar_profile(user):
    st.sidebar.markdown(f"""
    <div class="uldaemo-card" style="text-align: center; padding: 20px 16px;">
        <div style="font-size: 40px; margin-bottom: 6px;">{user['avatar'].split()[0]}</div>
        <div style="font-size: 18px; font-weight: 800; color: #191F28;">{user['nickname']} {'✅' if float(user['manner_temp']) >= 40.0 else ''}</div>
        <div style="font-size: 13px; color: #6B7684; margin-top: 2px; margin-bottom: 12px;">{user['department']} · {user['mbti']}</div>
        {MannerTemperature(user['manner_temp'])}
    </div>
    """, unsafe_allow_html=True)

    kws = get_dataframe(
        "SELECT keyword, count(*) as cnt FROM keyword_reviews WHERE reviewee_id=? GROUP BY keyword ORDER BY cnt DESC LIMIT 3",
        (user["student_id"],),
    )
    if not kws.empty:
        st.sidebar.markdown("**💖 받은 칭찬 키워드**")
        st.sidebar.markdown(PraiseTag([f"{r['keyword']} ({r['cnt']})" for _, r in kws.iterrows()]), unsafe_allow_html=True)

    if st.sidebar.button("로그아웃", key="sidebar_logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_id = ""
        st.session_state.verified_email = None
        try:
            controller.remove("user_id")
        except Exception:
            pass
        st.rerun()

# =========================================================
# 4. 앱 초기 설정 및 인증 (쿠키 적용)
# =========================================================
st.set_page_config(page_title="울대모 - 우리 학교, 가볍게 모여!", page_icon="🟢", layout="centered")
inject_design_tokens()

from streamlit_cookies_controller import CookieController
controller = CookieController()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "nav_tab" not in st.session_state:
    st.session_state.nav_tab = "홈"
if "active_modal" not in st.session_state:
    st.session_state.active_modal = None
if "selected_post_id" not in st.session_state:
    st.session_state.selected_post_id = None

try:
    stored_user_id = controller.get("user_id")
except Exception:
    stored_user_id = None

if stored_user_id and not st.session_state.logged_in:
    st.session_state.logged_in = True
    st.session_state.user_id = str(stored_user_id)
    st.rerun()

def verify_email():
    if "auth_code_sent" not in st.session_state:
        st.session_state.auth_code_sent = False
    if "verified_email" not in st.session_state:
        st.session_state.verified_email = None

    if st.session_state.verified_email:
        st.markdown(f"""
        <div class="privacy-badge" style="background:#EEF8F3; border-color:#287D62;">
            <span>✅</span>
            <span>학교 웹메일 인증 완료 ({st.session_state.verified_email})</span>
        </div>
        """, unsafe_allow_html=True)
        return st.session_state.verified_email

    st.markdown("<div style='font-size:13px; font-weight:700; color:#191F28; margin-bottom:4px;'>🔒 Step 1. 학교 웹메일 인증</div>", unsafe_allow_html=True)
    col_em, col_btn = st.columns([2.3, 1.1])
    with col_em:
        email = st.text_input("학교 웹메일", placeholder="student@ulsan.ac.kr", label_visibility="collapsed")
    with col_btn:
        if st.button("인증 요청", use_container_width=True):
            if email.strip().endswith(".ac.kr"):
                st.session_state.auth_code_sent = True
                st.toast("인증번호 [123456]이 발송되었습니다.")
            else:
                st.error("'.ac.kr' 학교 웹메일을 입력해주세요.")

    if st.session_state.auth_code_sent:
        st.caption("💡 데모 환경 안내: 인증번호 입력란에 **123456**을 입력해주세요.")
        col_c1, col_c2 = st.columns([2.3, 1.1])
        with col_c1:
            code = st.text_input("인증번호 6자리", placeholder="인증번호 6자리 (123456)", label_visibility="collapsed")
        with col_c2:
            if st.button("인증 확인", use_container_width=True, type="primary"):
                if code.strip() == "123456":
                    st.session_state.verified_email = email.strip()
                    st.rerun()
                else:
                    st.error("인증번호가 일치하지 않습니다.")
    return None

# =========================================================
# 로그인 & 온보딩 화면 (Figma 캠퍼스 그린 & 세이프 네트워킹 시안)
# =========================================================
if not st.session_state.logged_in:
    st.markdown(f"""
    <div class="uldaemo-card" style="background:linear-gradient(155deg, #287D62 0%, #1E634C 100%); color:#FFFFFF; padding:26px 22px; border:none; margin-top:8px; box-shadow:0 8px 20px rgba(40,125,98,0.22);">
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
            <div style="background:#FFFFFF; width:46px; height:46px; border-radius:14px; display:flex; align-items:center; justify-content:center;">
                {render_uldaemo_logo_svg(34)}
            </div>
            <div>
                <div style="font-size:24px; font-weight:900; letter-spacing:-0.5px; line-height:1.1;">울대모</div>
                <div style="font-size:12px; color:#DDF2E7; font-weight:600; margin-top:2px;">우리 학교, 가볍게 모여!</div>
            </div>
        </div>
        <div style="font-size:18px; font-weight:800; line-height:1.4; margin-bottom:8px;">
            공강 시간이나 방과 후,<br>함께할 학우를 안전하게 찾아요 🌱
        </div>
        <div style="font-size:12.5px; color:#E6F4EE; line-height:1.5; margin-bottom:16px;">
            방장 수락 전까지 익명이 보장되며, 매너 온도와 학우 인증으로 안심하고 만날 수 있는 울산대 전용 번개 플랫폼입니다.
        </div>
        <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; text-align:center;">
            <div style="background:rgba(255,255,255,0.13); border-radius:12px; padding:10px 6px;">
                <div style="font-size:18px;">🛡️</div>
                <div style="font-size:11.5px; font-weight:800; margin-top:3px;">안전한 만남</div>
                <div style="font-size:10px; color:#DDF2E7;">익명·안심채팅</div>
            </div>
            <div style="background:rgba(255,255,255,0.13); border-radius:12px; padding:10px 6px;">
                <div style="font-size:18px;">🍚</div>
                <div style="font-size:11.5px; font-weight:800; margin-top:3px;">다양한 활동</div>
                <div style="font-size:10px; color:#DDF2E7;">밥약·카공·운동</div>
            </div>
            <div style="background:rgba(255,255,255,0.13); border-radius:12px; padding:10px 6px;">
                <div style="font-size:18px;">🌡️</div>
                <div style="font-size:11.5px; font-weight:800; margin-top:3px;">매너 온도</div>
                <div style="font-size:10px; color:#DDF2E7;">학우 신뢰 지표</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    login_tab1, login_tab2 = st.tabs(["🔑 학번 로그인", "🎓 신규 학우 가입"])

    with login_tab1:
        with st.container(border=True):
            st.markdown("<div style='font-size:15px; font-weight:800; color:#191F28; margin-bottom:4px;'>학번으로 시작하기</div>", unsafe_allow_html=True)
            st.caption("가입된 학번을 입력하면 내 프로필과 매칭 내역으로 즉시 연결됩니다.")
            login_sid = st.text_input("학번 입력", placeholder="예: 20241001", key="login_sid_input")
            if st.button("울대모 시작하기", key="login_submit_btn", use_container_width=True, type="primary"):
                if not login_sid.strip():
                    st.warning("학번을 입력해주세요.")
                else:
                    found_u = get_dataframe("SELECT * FROM users WHERE student_id=?", (login_sid.strip(),))
                    if found_u.empty:
                        st.error("아직 등록되지 않은 학번입니다. 우측 '🎓 신규 학우 가입' 탭을 이용해주세요!")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user_id = login_sid.strip()
                        try:
                            controller.set("user_id", login_sid.strip())
                        except Exception:
                            pass
                        st.rerun()

        with st.container(border=True):
            st.markdown("<div style='font-size:13.5px; font-weight:800; color:#287D62; margin-bottom:2px;'>⚡ 원클릭 데모 계정으로 바로 체험하기</div>", unsafe_allow_html=True)
            st.caption("방장/참여자 화면과 매너 온도 시스템을 1초 만에 테스트해 볼 수 있습니다.")
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                if st.button("🐶 구름한점 (38.5°C)\n컴공 · ENFP", key="demo_login_1", use_container_width=True):
                    st.session_state.logged_in = True
                    st.session_state.user_id = "20241001"
                    try:
                        controller.set("user_id", "20241001")
                    except Exception:
                        pass
                    st.rerun()
            with d_col2:
                if st.button("🐱 노을이 (37.2°C)\n전자 · INFP", key="demo_login_2", use_container_width=True):
                    st.session_state.logged_in = True
                    st.session_state.user_id = "20241002"
                    try:
                        controller.set("user_id", "20241002")
                    except Exception:
                        pass
                    st.rerun()

    with login_tab2:
        with st.container(border=True):
            st.markdown("<div style='font-size:15px; font-weight:800; color:#191F28; margin-bottom:6px;'>신규 학우 블라인드 가입 (프로필 필수 목록)</div>", unsafe_allow_html=True)
            st.markdown(PrivacyBadge("방장 수락 전까지 실명과 이메일은 절대 외부에 노출되지 않습니다."), unsafe_allow_html=True)
            new_student_id = st.text_input("학번 (아이디) (필수)", placeholder="예: 20240001", key="signup_sid_input")
            verified_email = verify_email()

            st.divider()
            st.markdown("<div style='font-size:13px; font-weight:700; color:#191F28; margin-bottom:6px;'>👤 Step 2. 블라인드 프로필 작성 (필수 항목)</div>", unsafe_allow_html=True)
            user_nickname = st.text_input("닉네임 (익명 표시용) (필수)", placeholder="예: 푸른솔", key="signup_nick_input")
            c_p1, c_p2 = st.columns(2)
            with c_p1:
                user_avatar = st.selectbox("프로필 아바타 (필수)", ["🐶 강아지", "🐱 고양이", "🦊 여우", "🐻 곰", "🐰 토끼", "🐹 햄스터"], key="signup_avatar_select")
                user_gender = st.selectbox("성별 (필수)", ["남성", "여성"], key="signup_gender_select")
            with c_p2:
                user_dept = st.text_input("학과 (필수)", value="컴퓨터공학과", key="signup_dept_input")
                user_mbti = st.selectbox("MBTI (필수)", ["ENFP", "ENTP", "INFP", "INTP", "ESFJ", "ESTJ", "ISFJ", "ISTJ", "ENFJ", "ENTJ", "INFJ", "INTJ", "ESFP", "ESTP", "ISFP", "ISTP", "모름/비공개"], key="signup_mbti_select")

            if st.button("🌱 가입 완료 및 울대모 시작하기", key="signup_submit_btn", use_container_width=True, type="primary"):
                if not new_student_id.strip():
                    st.warning("학번 (필수)을 입력해주세요.")
                elif not verified_email:
                    st.warning("먼저 Step 1 학교 웹메일 인증 (필수)을 완료해주세요.")
                elif not user_nickname.strip():
                    st.warning("닉네임 (필수)을 입력해주세요.")
                elif not user_dept.strip():
                    st.warning("학과 (필수)를 입력해주세요.")
                else:
                    execute_commit("""
                        INSERT INTO users (student_id, email, is_verified, nickname, avatar, gender, department, mbti)
                        VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                        ON CONFLICT(student_id) DO UPDATE SET 
                        email=?, nickname=?, avatar=?, gender=?, department=?, mbti=?
                    """, (
                        new_student_id.strip(), verified_email, user_nickname.strip(), user_avatar, user_gender, user_dept.strip(), user_mbti,
                        verified_email, user_nickname.strip(), user_avatar, user_gender, user_dept.strip(), user_mbti
                    ))
                    st.session_state.logged_in = True
                    st.session_state.user_id = new_student_id.strip()
                    try:
                        controller.set("user_id", new_student_id.strip())
                    except Exception:
                        pass
                    st.rerun()
    st.stop()

# =========================================================
# 5. 로그인 사용자 정보 로드 및 하단/상단 네비게이션 구성
# =========================================================
user_info = get_dataframe("SELECT * FROM users WHERE student_id = ?", (st.session_state.user_id,))
if user_info.empty:
    st.session_state.logged_in = False
    st.rerun()

user = user_info.iloc[0]
if int(user["report_count"]) >= 3:
    st.error("🚨 누적 신고 3회 이상으로 계정이 일시 정지되었습니다. 관리자에게 문의하세요.")
    st.stop()

render_sidebar_profile(user)

unreads_df = get_dataframe("SELECT count(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0", (st.session_state.user_id,))
unread_cnt = int(unreads_df.iloc[0]["cnt"]) if not unreads_df.empty else 0

AppHeader(unread_cnt)

# 하단 고정형 탭 내비게이션 바 (홈 / 지도 / 채팅 / 마이)
def BottomNavigation():
    nav_items = [
        ("홈", "🏠 홈"),
        ("지도", "🗺️ 지도"),
        ("채팅", f"💬 채팅{' •' if unread_cnt > 0 else ''}"),
        ("마이", "👤 마이"),
    ]
    cols = st.columns(4)
    for idx, (nav_key, nav_label) in enumerate(nav_items):
        is_current = (st.session_state.nav_tab == nav_key) and (st.session_state.active_modal is None)
        if cols[idx].button(
            nav_label,
            key=f"bottom_nav_{nav_key}",
            use_container_width=True,
            type="primary" if is_current else "secondary",
        ):
            st.session_state.nav_tab = nav_key
            st.session_state.active_modal = None
            st.rerun()

BottomNavigation()
st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

now = datetime.now()
KW_OPTIONS = ["시간 약속을 잘 지켜요 ⏰", "친절해요 😊", "적극적이에요 👍", "대화가 즐거워요 💬", "조용히 집중하기 좋아요 📚"]

# =========================================================
# 서브 화면 1: 번개 모집하기 폼 (Create Meetup View)
# =========================================================
if st.session_state.active_modal == "create":
    if st.button("← 홈으로 돌아가기", key="back_from_create"):
        st.session_state.active_modal = None
        st.rerun()

    st.markdown("### ➕ 새로운 번개 모집하기")
    st.markdown(PrivacyBadge("방장이 수락하기 전까지 내 실명과 연락처는 절대 노출되지 않습니다."), unsafe_allow_html=True)

    with st.container(border=True):
        st.caption("💡 활동 카테고리·만날 장소·만남 성향 태그는 목록에서 고르거나, **칸에 직접 타이핑한 뒤 Enter**를 치면 자유롭게 입력됩니다!")
        title = st.text_input("모집 제목", placeholder="예: 학식 같이 먹고 다음 수업 가요!", key="create_title")

        category_choice = st.selectbox(
            "활동 카테고리 (목록 선택 또는 직접 타이핑 후 Enter)",
            [
                "🍚 밥약", "☕ 카공", "🏃 운동", "🚶 산책",
                "🎮 게임/PC방", "🎤 코노/노래방", "🎲 보드게임",
                "🎬 영화/문화", "🚕 택시 합승", "🍺 가벼운 술약"
            ],
            accept_new_options=True,
            key="create_cat_select",
        )

        c1, c2 = st.columns(2)
        with c1:
            meet_date = st.date_input("모임 날짜", min_value=date.today(), key="create_date")
            meet_time = st.time_input("모임 시간", value=datetime.strptime("12:30", "%H:%M").time(), key="create_time")
        with c2:
            ulsan_buildings = list(ULSAN_CAMPUS_COORDS.keys())
            default_idx = ulsan_buildings.index("22호관 학생회관") if "22호관 학생회관" in ulsan_buildings else 0
            loc_preset = st.selectbox(
                "만날 장소 (호관 검색 또는 직접 타이핑 후 Enter)",
                ulsan_buildings,
                index=default_idx,
                accept_new_options=True,
                key="create_loc_select",
            )
            max_participants = st.number_input("최대 모집 인원", min_value=1, max_value=10, value=3, key="create_max_p")

        meeting_style = st.selectbox(
            "만남 성향 태그 (목록 선택 또는 직접 타이핑 후 Enter)",
            [
                "간단한 스몰토크 환영",
                "이어폰 꽂고 조용히 각자 할일",
                "텐션 높게 E처럼 놀아요",
                "정보 공유 및 진지한 대화",
                "밥만 빠르게 먹고 헤어져요 (쿨거래형)",
                "초보자도 대환영! 같이 배워요",
            ],
            accept_new_options=True,
            key="create_style_select",
        )

        if st.button("🚀 번개 모집 등록하기", key="submit_create_post", use_container_width=True, type="primary"):
            final_cat = str(category_choice).strip() if category_choice else ""
            final_loc = str(loc_preset).strip() if loc_preset else ""
            final_style = str(meeting_style).strip() if meeting_style else ""

            if len(title.strip()) < 2:
                st.error("모집 제목은 최소 2글자 이상 입력해주세요.")
            elif meet_date < date.today():
                st.error("과거 날짜로는 번개 모임을 등록할 수 없습니다.")
            elif not final_cat:
                st.error("활동 카테고리를 입력하거나 선택해주세요.")
            elif not final_loc:
                st.error("만날 장소를 입력하거나 선택해주세요.")
            elif not final_style:
                st.error("만남 성향 태그를 입력하거나 선택해주세요.")
            else:
                execute_commit("""
                    INSERT INTO posts (author_id, title, category, meet_date, meet_time, location, max_participants, meeting_style, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, '모집중')
                """, (
                    st.session_state.user_id, title.strip(), final_cat,
                    meet_date.strftime("%Y-%m-%d"), meet_time.strftime("%H:%M"),
                    final_loc, int(max_participants), final_style
                ))
                st.toast("번개 모집이 등록되었습니다!")
                st.session_state["home_cat"] = "전체"
                st.session_state.active_modal = None
                st.session_state.nav_tab = "홈"
                st.rerun()
    st.stop()

# =========================================================
# 화면 B: 모집 상세 화면 (MeetupDetail View)
# =========================================================
if st.session_state.active_modal == "detail" and st.session_state.selected_post_id is not None:
    if st.button("← 목록으로 돌아가기", key="back_from_detail"):
        st.session_state.active_modal = None
        st.rerun()

    detail_df = get_dataframe("""
        SELECT p.*, u.nickname, u.avatar, u.manner_temp, u.mbti, u.department
        FROM posts p JOIN users u ON p.author_id = u.student_id
        WHERE p.id = ?
    """, (st.session_state.selected_post_id,))

    if detail_df.empty:
        EmptyState("존재하지 않거나 삭제된 모임입니다.")
        st.stop()

    post = detail_df.iloc[0]
    badge_label, meta = format_category_badge(post["category"])
    apps_df = get_dataframe("""
        SELECT a.id as app_id, a.applicant_id, a.status, u.nickname, u.avatar, u.department, u.mbti, u.manner_temp
        FROM applications a JOIN users u ON a.applicant_id = u.student_id
        WHERE a.post_id = ?
    """, (post["id"],))
    accepted_cnt = len(apps_df[apps_df["status"] == "승인됨"])
    my_app_rows = apps_df[apps_df["applicant_id"] == str(st.session_state.user_id)]
    my_app_status = my_app_rows.iloc[0]["status"] if not my_app_rows.empty else None
    host_kws = get_user_top_keywords(post["author_id"], limit=3)

    # 1. 상단 대표 일러스트 & 모집 헤더 카드
    st.markdown(f"""
    <div class="uldaemo-card">
        <div style="background:linear-gradient(135deg, {meta['chip_bg']} 0%, #EEF8F3 100%); height:110px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:46px; margin-bottom:14px;">
            {meta['icon']}
        </div>
        <span style="background:{meta['chip_bg']}; color:{meta['chip_fg']}; font-size:12px; font-weight:800; padding:4px 10px; border-radius:999px;">
            {badge_label}
        </span>
        <h3 style="margin:10px 0 8px 0; font-size:20px; font-weight:800; color:#191F28;">{post['title']}</h3>
        <div style="font-size:13px; color:#4E5968; display:flex; flex-wrap:wrap; gap:12px;">
            <span>🕒 <b>{post['meet_date']} {post['meet_time']}</b></span>
            <span>📍 <b>{post['location']}</b></span>
            <span>👥 <b>{accepted_cnt} / {post['max_participants']}명</b></span>
        </div>
        {PrivacyBadge("방장 수락 전까지 익명 보장됩니다.")}
    </div>
    """, unsafe_allow_html=True)

    # 2. 방장 프로필 요약 카드 (ProfileSummary)
    st.markdown(f"""
    <div class="uldaemo-card">
        <div style="font-size:12px; font-weight:700; color:#6B7684; margin-bottom:8px;">👑 방장 프로필</div>
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
            <div style="font-size:34px; background:#F7F8F4; width:52px; height:52px; border-radius:50%; display:flex; align-items:center; justify-content:center;">
                {post['avatar'].split()[0]}
            </div>
            <div style="flex:1;">
                <div style="font-size:16px; font-weight:800; color:#191F28;">
                    {post['nickname']} {'✅' if float(post['manner_temp']) >= 40.0 else ''}
                </div>
                <div style="font-size:12.5px; color:#6B7684;">{post['department']} · {post['mbti']}</div>
            </div>
        </div>
        {MannerTemperature(post['manner_temp'])}
        {PraiseTag(host_kws)}
    </div>
    """, unsafe_allow_html=True)

    # 3. 모집 정보 & 실제 인터랙티브 캠퍼스 지도 미리보기 카드
    st.markdown(f"""
    <div class="uldaemo-card" style="margin-bottom:8px;">
        <div style="font-size:14px; font-weight:800; color:#191F28; margin-bottom:10px;">📋 모집 상세 정보</div>
        <div style="font-size:13px; color:#4E5968; line-height:1.9;">
            <div>• <b>활동 종류:</b> {post['category']} ({post['meeting_style']})</div>
            <div>• <b>만남 장소:</b> {post['location']}</div>
            <div>• <b>모임 시간:</b> {post['meet_date']} {post['meet_time']}</div>
            <div>• <b>모집 인원:</b> 현재 {accepted_cnt}명 수락 / 최대 {post['max_participants']}명</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    d_lat, d_lng, _ = resolve_campus_location(post["location"])
    d_search = post["location"].split("호관 ", 1)[1] if "호관 " in str(post["location"]) else post["location"]
    d_kakao_url = f"https://map.kakao.com/link/search/{urllib.parse.quote('울산대학교 ' + str(d_search))}"

    st.components.v1.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8"/>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body {{ margin:0; padding:0; font-family:'Pretendard', sans-serif; }}
            #detail-map {{ width:100%; height:195px; border-radius:16px; border:1px solid #C5E6D6; box-sizing:border-box; }}
            .pin-wrap {{
                position: relative;
                transform: translate(-50%, -100%);
                display: inline-flex;
                flex-direction: column;
                align-items: center;
                pointer-events: auto;
            }}
            .pin-badge {{
                background:#287D62; color:#FFFFFF; font-weight:800; font-size:12px;
                padding:5px 11px; border-radius:999px; border:2px solid #FFFFFF;
                box-shadow:0 3px 10px rgba(40,125,98,0.38); white-space:nowrap;
            }}
            .pin-tail {{
                width: 0; height: 0;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 8px solid #287D62;
                margin-top: -1px;
            }}
            .pin-dot {{
                width: 7px; height: 7px;
                background: #287D62;
                border: 2px solid #FFFFFF;
                border-radius: 50%;
                box-shadow: 0 1px 4px rgba(0,0,0,0.3);
                margin-top: 1px;
            }}
        </style>
    </head>
    <body>
        <div id="detail-map"></div>
        <script>
            var map = L.map('detail-map', {{ zoomControl: true }}).setView([{d_lat}, {d_lng}], 17);
            map.attributionControl.setPrefix(false);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                attribution: '울산대 캠퍼스맵'
            }}).addTo(map);
            var icon = L.divIcon({{
                className: '',
                html: '<div class="pin-wrap"><div class="pin-badge">📍 {post["location"]}</div><div class="pin-tail"></div><div class="pin-dot"></div></div>',
                iconSize: [0, 0],
                iconAnchor: [0, 0],
                popupAnchor: [0, -42]
            }});
            L.marker([{d_lat}, {d_lng}], {{icon: icon}}).addTo(map)
                .bindPopup('<b>{post["location"]}</b><br>{post["title"]}<br><a href="{d_kakao_url}" target="_blank" style="color:#287D62;font-weight:bold;">카카오맵 길찾기 →</a>');
        </script>
    </body>
    </html>
    """, height=205)

    st.markdown(f"<div style='text-align:center; margin-top:-4px; margin-bottom:12px;'>{KakaoMapButton(post['location'], '🗺️ 카카오맵으로 길찾기 열기')}</div>", unsafe_allow_html=True)

    # 4. 방장 권한 관리 또는 참여자 신청 버튼
    if str(post["author_id"]) == str(st.session_state.user_id):
        with st.container(border=True):
            st.markdown("#### 👑 방장 전용: 신청자 수락 및 모임 관리")
            if apps_df.empty:
                st.caption("아직 참여를 신청한 학우가 없습니다.")
            else:
                for _, app_row in apps_df.iterrows():
                    st.markdown(
                        f"**{app_row['avatar']} {app_row['nickname']}** ({app_row['department']} · {app_row['mbti']} · 🌡️{app_row['manner_temp']:.1f}°C) — 상태: `{app_row['status']}`"
                    )
                    if app_row["status"] == "대기중" and accepted_cnt < int(post["max_participants"]):
                        if st.button(f"✅ {app_row['nickname']}님 수락하기", key=f"detail_accept_{app_row['app_id']}", type="primary"):
                            execute_commit("UPDATE applications SET status='승인됨' WHERE id=?", (app_row["app_id"],))
                            notify_user(app_row["applicant_id"], f"[{post['title']}] 참여 신청이 수락되었습니다! 안심 채팅방을 확인하세요.")
                            if accepted_cnt + 1 >= int(post["max_participants"]):
                                execute_commit("UPDATE posts SET status='매칭완료' WHERE id=?", (post["id"],))
                            st.rerun()

            with st.expander("✏️ 모집 내용(제목·장소·시간·인원) 수정하기"):
                edit_title = st.text_input("모집 제목 수정", value=str(post["title"]), key=f"edit_post_title_{post['id']}")
                b_opts = list(ULSAN_CAMPUS_COORDS.keys())
                if str(post["location"]) not in b_opts:
                    b_opts = [str(post["location"])] + b_opts
                edit_loc = st.selectbox(
                    "만날 장소 수정 (직접 입력 가능)",
                    b_opts,
                    index=b_opts.index(str(post["location"])),
                    accept_new_options=True,
                    key=f"edit_post_loc_{post['id']}",
                )
                ec1, ec2 = st.columns(2)
                with ec1:
                    edit_time_str = st.text_input("모임 시간 (HH:MM)", value=str(post["meet_time"]), key=f"edit_post_time_{post['id']}")
                with ec2:
                    edit_max_p = st.number_input("최대 인원", min_value=1, max_value=10, value=int(post["max_participants"]), key=f"edit_post_max_{post['id']}")
                if st.button("💾 수정사항 저장", key=f"save_edit_post_{post['id']}", use_container_width=True, type="primary"):
                    if len(edit_title.strip()) < 2:
                        st.error("모집 제목은 2글자 이상 입력해주세요.")
                    else:
                        execute_commit(
                            "UPDATE posts SET title=?, location=?, meet_time=?, max_participants=? WHERE id=?",
                            (edit_title.strip(), str(edit_loc).strip(), edit_time_str.strip(), int(edit_max_p), post["id"]),
                        )
                        st.toast("모집 내용이 수정되었습니다!")
                        st.rerun()

            c_m1, c_m2 = st.columns(2)
            with c_m1:
                if st.button("🔒 모집 조기 마감", key=f"detail_close_{post['id']}", use_container_width=True):
                    execute_commit("UPDATE posts SET status='매칭완료' WHERE id=?", (post["id"],))
                    st.toast("모집이 마감 처리되었습니다.")
                    st.session_state.active_modal = None
                    st.rerun()
            with c_m2:
                if st.button("🗑️ 모임 삭제(취소)", key=f"detail_cancel_{post['id']}", use_container_width=True):
                    execute_commit("DELETE FROM applications WHERE post_id=?", (post["id"],))
                    execute_commit("DELETE FROM posts WHERE id=?", (post["id"],))
                    st.toast("모집글이 삭제되었습니다.")
                    st.session_state.active_modal = None
                    st.rerun()
    else:
        if my_app_status == "승인됨":
            st.success("🎉 방장이 신청을 수락했습니다! 지금 안심 채팅방에서 대화해 보세요.")
            if st.button("💬 안심 채팅방으로 이동", key="detail_go_chat", use_container_width=True, type="primary"):
                st.session_state.active_modal = None
                st.session_state.nav_tab = "채팅"
                st.rerun()
        elif my_app_status == "대기중":
            st.info("⏳ 현재 방장의 수락을 기다리고 있습니다. 수락 전까지 내 실명/연락처는 보호됩니다.")
            if st.button("신청 취소하기", key="detail_cancel_my_app", use_container_width=True):
                execute_commit(
                    "DELETE FROM applications WHERE post_id=? AND applicant_id=?",
                    (post["id"], st.session_state.user_id),
                )
                st.rerun()
        elif accepted_cnt >= int(post["max_participants"]) or post["status"] != "모집중":
            st.button("모집이 마감되었습니다", key="detail_closed_btn", use_container_width=True, disabled=True)
        else:
            if st.button("참여 신청하기", key="detail_apply_now", use_container_width=True, type="primary"):
                execute_commit(
                    "INSERT INTO applications (post_id, applicant_id, status) VALUES (?, ?, '대기중')",
                    (post["id"], st.session_state.user_id),
                )
                notify_user(post["author_id"], f"[{post['title']}] 모임에 {user['nickname']}님이 참여를 신청했습니다!")
                st.rerun()
    st.stop()

# =========================================================
# 화면 A: 홈 화면 (Main Feed)
# =========================================================
if st.session_state.nav_tab == "홈":
    MainBanner()

    # 활동 카테고리 필터 (전체 / 밥약 / 카공 / 운동 / 산책)
    selected_cat = CategoryFilter("home_cat")

    # 검색 & 오늘의 번개 필터 바
    s_col1, s_col2 = st.columns([2.2, 1.2])
    with s_col1:
        search_kw = st.text_input("🔍 키워드 검색", placeholder="🔍 제목·장소 검색 (예: 학식, 도서관)", label_visibility="collapsed")
    with s_col2:
        only_today = st.toggle("⚡ 오늘 번개만", value=False)

    st.markdown("""
    <div style="display:flex; justify-content:space-between; align-items:center; margin: 10px 0 8px 0;">
        <span style="font-size:17px; font-weight:800; color:#191F28;">지금 모집 중</span>
        <span style="font-size:12px; color:#287D62; font-weight:700;">실시간 업데이트</span>
    </div>
    """, unsafe_allow_html=True)

    posts_df = get_dataframe("""
        SELECT p.id, p.title, p.category, p.meet_date, p.meet_time, p.location, p.max_participants, p.meeting_style, p.status, p.author_id,
               u.nickname, u.avatar, u.manner_temp, u.mbti, u.department
        FROM posts p JOIN users u ON p.author_id = u.student_id
        WHERE p.status = '모집중'
        ORDER BY p.id DESC
    """)

    my_apps_map = {}
    my_apps_df = get_dataframe("SELECT post_id, status FROM applications WHERE applicant_id=?", (st.session_state.user_id,))
    for _, ar in my_apps_df.iterrows():
        my_apps_map[int(ar["post_id"])] = ar["status"]

    rendered_count = 0
    for _, row in posts_df.iterrows():
        # 만료 체크 (모임 시간 + 24시간 경과 시 자동 만료)
        try:
            post_dt = datetime.strptime(f"{row['meet_date']} {row['meet_time']}", "%Y-%m-%d %H:%M")
            if post_dt + timedelta(hours=24) < now:
                execute_commit("UPDATE posts SET status='만료됨' WHERE id=?", (row["id"],))
                continue
        except Exception:
            pass

        norm_cat = normalize_category(row["category"])
        if selected_cat != "전체" and norm_cat != selected_cat:
            continue
        if only_today and row["meet_date"] != date.today().strftime("%Y-%m-%d"):
            continue
        if search_kw.strip():
            kw = search_kw.strip().lower()
            searchable = f"{row['title']} {row['location']} {row['category']} {row['meeting_style']}".lower()
            if kw not in searchable:
                continue

        acc_df = get_dataframe("SELECT count(*) as cnt FROM applications WHERE post_id=? AND status='승인됨'", (row["id"],))
        acc_cnt = int(acc_df.iloc[0]["cnt"]) if not acc_df.empty else 0

        MeetupCard(row, acc_cnt, my_apps_map.get(int(row["id"])), key_prefix="home")
        rendered_count += 1

    if rendered_count == 0:
        EmptyState("조건에 맞는 번개 모임이 없어요", "다른 카테고리를 선택하거나 직접 번개를 열어보세요!")

    # 5. 캠퍼스 지도 진입 배너 영역
    st.markdown("""
    <div class="uldaemo-card" style="background:#EEF8F3; border-color:#C5E6D6; margin-top:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="font-size:13.5px; font-weight:800; color:#191F28;">🗺️ 캠퍼스에서 어디서 만날까?</div>
                <div style="font-size:12px; color:#287D62; margin-top:2px;">주변 모집과 만날 장소를 캠퍼스 지도에서 확인해요.</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🗺️ 캠퍼스 지도에서 주변 모집 보기 →", key="home_to_map_btn", use_container_width=True):
        st.session_state.nav_tab = "지도"
        st.rerun()

# =========================================================
# 화면 C: 캠퍼스 지도 화면 (CampusMap View - 실제 인터랙티브 지도)
# =========================================================
elif st.session_state.nav_tab == "지도":
    st.markdown("### 🗺️ 캠퍼스 지도")
    with st.container(border=True):
        st.markdown("<div style='font-size:13.5px; font-weight:800; color:#191F28; margin-bottom:4px;'>📍 위치 정보 수집 설정 및 장소 선택</div>", unsafe_allow_html=True)
        loc_consent = st.toggle(
            "📍 위치 정보 수집 및 내 현위치 표시 동의 (GPS 연동)",
            value=st.session_state.get("location_consent", True),
            key="map_location_consent_toggle",
        )
        st.session_state.location_consent = loc_consent

        my_loc_mode = "📡 기기 GPS 실시간 자동 감지"
        if loc_consent:
            st.caption("✅ 위치 정보 수집 활성화됨: 기기 GPS로 내 위치를 찾거나, PC 오차 시 아래에서 현재 계신 건물을 직접 지정·지도에서 파란 핀(🔵)을 드래그해 보정할 수 있습니다.")
            my_loc_options = ["📡 기기 GPS 실시간 자동 감지"] + list(ULSAN_CAMPUS_COORDS.keys())
            my_loc_mode = st.selectbox(
                "🧭 내 현위치 기준 설정 (PC 접속 시 현재 있는 건물 선택 또는 직접 입력 가능)",
                my_loc_options,
                index=0,
                accept_new_options=True,
                key="map_my_loc_selector",
            )
        else:
            st.caption("🔒 위치 정보 수집 비활성화됨: 내 현위치 표시 없이 캠퍼스 건물 기준으로만 지도를 탐색합니다.")

        place_options = ["전체 캠퍼스 보기"] + list(ULSAN_CAMPUS_COORDS.keys())
        selected_map_place = st.selectbox(
            "📌 캠퍼스 장소 선택 (모집 글 필터링 · 건물 선택 또는 새 장소 직접 입력)",
            place_options,
            index=0,
            accept_new_options=True,
            key="map_place_selector",
        )

    map_search = st.text_input("🔍 장소 검색하기", placeholder="🔍 건물명 또는 장소 검색 (예: 학생회관, 아산도서관)", label_visibility="collapsed")
    map_cat = CategoryFilter("map_cat")

    active_place_filter = ""
    if selected_map_place and selected_map_place != "전체 캠퍼스 보기":
        active_place_filter = selected_map_place.strip()
    elif map_search.strip():
        active_place_filter = map_search.strip()

    # 내 현위치 좌표 계산 (수동 건물/장소 지정 시 해당 실제 좌표 사용, 자동 모드 시 브라우저 GPS 호출)
    use_auto_gps = True
    my_init_lat, my_init_lng = 35.544432, 129.256411  # 기본 폴백: 22호관 학생회관 정중앙
    my_loc_label = "내 현위치"
    if loc_consent and my_loc_mode and my_loc_mode != "📡 기기 GPS 실시간 자동 감지":
        use_auto_gps = False
        my_init_lat, my_init_lng, _ = resolve_campus_location(my_loc_mode)
        short_my = my_loc_mode.split("호관 ", 1)[1] if "호관 " in my_loc_mode else my_loc_mode
        my_loc_label = f"내 현위치 ({short_my})"

    map_posts = get_dataframe("""
        SELECT p.id, p.title, p.category, p.meet_date, p.meet_time, p.location, p.max_participants, p.meeting_style, p.status, p.author_id,
               u.nickname, u.avatar, u.manner_temp, u.mbti, u.department
        FROM posts p JOIN users u ON p.author_id = u.student_id
        WHERE p.status = '모집중'
        ORDER BY p.id DESC
    """)

    markers_data = []
    grouped_locs = {}
    for _, r in map_posts.iterrows():
        ncat = normalize_category(r["category"])
        if map_cat != "전체" and ncat != map_cat:
            continue
        if active_place_filter and active_place_filter.lower() not in str(r["location"]).lower() and active_place_filter.lower() not in str(r["title"]).lower():
            continue
        loc_key = str(r["location"])
        if loc_key not in grouped_locs:
            grouped_locs[loc_key] = {"count": 0, "titles": [], "cat": ncat}
        grouped_locs[loc_key]["count"] += 1
        grouped_locs[loc_key]["titles"].append(str(r["title"]))

    # 장소 선택 또는 검색어가 입력된 경우 모집 글이 0건인 건물/장소라도 지도에서 위치를 바로 확인할 수 있도록 마커 표시
    if active_place_filter:
        q_lower = active_place_filter.lower()
        matched_building = False
        for b_name in ULSAN_CAMPUS_COORDS.keys():
            if q_lower in b_name.lower() and b_name not in grouped_locs:
                grouped_locs[b_name] = {"count": 0, "titles": ["선택한 장소 위치 확인"], "cat": "선택장소"}
                matched_building = True
        if not matched_building and active_place_filter not in grouped_locs:
            grouped_locs[active_place_filter] = {"count": 0, "titles": ["직접 입력한 장소 위치"], "cat": "선택장소"}

    for loc_name, info in grouped_locs.items():
        lat, lng, icon_em = resolve_campus_location(loc_name)
        short_name = loc_name.split("호관 ", 1)[1] if "호관 " in loc_name else loc_name
        kakao_q = urllib.parse.quote(f"울산대학교 {short_name}")
        markers_data.append({
            "name": short_name,
            "full_name": loc_name,
            "lat": lat,
            "lng": lng,
            "icon": icon_em,
            "cat": info["cat"],
            "count": info["count"],
            "sample_title": info["titles"][0] if info["titles"] else "",
            "kakao_url": f"https://map.kakao.com/link/search/{kakao_q}",
        })

    markers_json = json.dumps(markers_data, ensure_ascii=False)
    loc_consent_js = "true" if loc_consent else "false"
    use_auto_gps_js = "true" if use_auto_gps else "false"
    my_loc_label_json = json.dumps(my_loc_label, ensure_ascii=False)
    total_active = sum(m["count"] for m in markers_data)

    # 실제 드래그·확대/축소가 가능한 울산대학교 인터랙티브 지도 렌더링 (Leaflet + OSM)
    st.components.v1.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8"/>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body {{ margin:0; padding:0; font-family:'Pretendard', -apple-system, sans-serif; }}
            #campus-map {{
                width: 100%;
                height: 290px;
                border-radius: 16px;
                border: 1px solid #C5E6D6;
                box-shadow: 0 2px 10px rgba(25,31,40,0.06);
                box-sizing: border-box;
                position: relative;
            }}
            .pin-wrap {{
                position: relative;
                transform: translate(-50%, -100%);
                display: inline-flex;
                flex-direction: column;
                align-items: center;
                pointer-events: auto;
            }}
            .uldaemo-marker {{
                background: #287D62;
                color: #FFFFFF;
                border: 2px solid #FFFFFF;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11.5px;
                font-weight: 800;
                white-space: nowrap;
                box-shadow: 0 3px 10px rgba(40,125,98,0.38);
                display: inline-flex;
                align-items: center;
                gap: 3px;
            }}
            .uldaemo-marker span.cnt {{
                background: #DDF2E7;
                color: #287D62;
                border-radius: 999px;
                padding: 1px 6px;
                font-size: 10.5px;
                margin-left: 2px;
            }}
            .pin-tail {{
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 7px solid #287D62;
                margin-top: -1px;
            }}
            .pin-dot {{
                width: 7px; height: 7px;
                background: #287D62;
                border: 2px solid #FFFFFF;
                border-radius: 50%;
                box-shadow: 0 1px 4px rgba(0,0,0,0.35);
                margin-top: 1px;
            }}
            .my-loc-pill {{
                background: #1B64DA;
                color: #FFFFFF;
                border: 2px solid #FFFFFF;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11.5px;
                font-weight: 800;
                white-space: nowrap;
                box-shadow: 0 3px 10px rgba(27,100,218,0.45);
            }}
            .my-pin-tail {{
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 7px solid #1B64DA;
                margin-top: -1px;
            }}
            .my-pin-dot {{
                width: 9px; height: 9px;
                background: #1B64DA;
                border: 2px solid #FFFFFF;
                border-radius: 50%;
                box-shadow: 0 0 0 4px rgba(27,100,218,0.28);
                margin-top: 1px;
            }}
            .gps-btn {{
                position: absolute;
                top: 10px;
                right: 10px;
                z-index: 1000;
                background: #FFFFFF;
                color: #191F28;
                border: 1px solid #C5E6D6;
                border-radius: 999px;
                padding: 5px 10px;
                font-size: 11.5px;
                font-weight: 800;
                cursor: pointer;
                box-shadow: 0 2px 6px rgba(0,0,0,0.12);
            }}
        </style>
    </head>
    <body>
        <div id="campus-map">
            <button class="gps-btn" id="gps-find-btn" onclick="findMyCampusLocation(true)">🎯 내 위치 찾기</button>
        </div>
        <script>
            var map = L.map('campus-map').setView([{my_init_lat}, {my_init_lng}], 16);
            map.attributionControl.setPrefix(false);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                attribution: '울산대 캠퍼스맵'
            }}).addTo(map);

            var markers = {markers_json};
            var locConsent = {loc_consent_js};
            var useAutoGps = {use_auto_gps_js};
            var myLocLabel = {my_loc_label_json};
            var latlngs = [];
            markers.forEach(function(m) {{
                latlngs.push([m.lat, m.lng]);
                var customIcon = L.divIcon({{
                    className: '',
                    html: '<div class="pin-wrap"><div class="uldaemo-marker">' + m.icon + ' ' + m.name + ' <span class="cnt">' + m.cat + ' ' + m.count + '건</span></div><div class="pin-tail"></div><div class="pin-dot"></div></div>',
                    iconSize: [0, 0],
                    iconAnchor: [0, 0],
                    popupAnchor: [0, -40]
                }});
                var popupHtml = '<div style="font-size:13px; line-height:1.5;">' +
                    '<b style="color:#287D62;">📍 ' + m.full_name + '</b> (' + m.count + '건 모집 중)<br>' +
                    '<span>• ' + m.sample_title + '</span><br>' +
                    '<a href="' + m.kakao_url + '" target="_blank" style="color:#287D62; font-weight:bold; text-decoration:none;">🗺️ 카카오맵 길찾기 열기 →</a>' +
                    '</div>';
                L.marker([m.lat, m.lng], {{icon: customIcon}}).addTo(map).bindPopup(popupHtml);
            }});

            var myLocMarker = null;
            var myAccCircle = null;
            function renderMyLoc(lat, lng, labelText, accMeters) {{
                if (myLocMarker) {{ map.removeLayer(myLocMarker); }}
                if (myAccCircle) {{ map.removeLayer(myAccCircle); }}
                var dispLabel = labelText || myLocLabel || '내 현위치';
                var myIcon = L.divIcon({{
                    className: '',
                    html: '<div class="pin-wrap"><div class="my-loc-pill">🔵 ' + dispLabel + '</div><div class="my-pin-tail"></div><div class="my-pin-dot"></div></div>',
                    iconSize: [0, 0],
                    iconAnchor: [0, 0],
                    popupAnchor: [0, -40]
                }});
                myLocMarker = L.marker([lat, lng], {{icon: myIcon, draggable: true, zIndexOffset: 900}}).addTo(map);
                myLocMarker.bindPopup('<b>🔵 ' + dispLabel + '</b><br><span style="font-size:11.5px;color:#4E5968;">핀을 마우스로 드래그하면 내 위치를 미세 조정할 수 있습니다.</span>');
                myLocMarker.on('dragend', function(e) {{
                    var p = e.target.getLatLng();
                    myLocMarker.setPopupContent('<b>🔵 내 현위치 (직접 보정됨)</b><br><span style="font-size:11.5px;color:#4E5968;">위도 ' + p.lat.toFixed(5) + ', 경도 ' + p.lng.toFixed(5) + '</span>').openPopup();
                }});
                if (accMeters && accMeters < 500) {{
                    myAccCircle = L.circle([lat, lng], {{radius: accMeters, color: '#1B64DA', fillColor: '#1B64DA', fillOpacity: 0.1, weight: 1}}).addTo(map);
                }}
            }}

            function getGeoObject() {{
                try {{
                    if (window.parent && window.parent.navigator && window.parent.navigator.geolocation) {{
                        return window.parent.navigator.geolocation;
                    }}
                }} catch (e) {{}}
                return navigator.geolocation;
            }}

            function findMyCampusLocation(panToMe) {{
                if (!locConsent) {{
                    if (panToMe) alert('상단의 [위치 정보 수집 및 내 현위치 표시 동의] 설정을 먼저 켜주세요.');
                    return;
                }}
                if (!useAutoGps) {{
                    renderMyLoc({my_init_lat}, {my_init_lng}, myLocLabel, 25);
                    if (panToMe) map.setView([{my_init_lat}, {my_init_lng}], 17);
                    return;
                }}
                var geo = getGeoObject();
                var btn = document.getElementById('gps-find-btn');
                if (geo) {{
                    if (btn && panToMe) btn.innerText = '📡 GPS 수신 중...';
                    geo.getCurrentPosition(function(pos) {{
                        if (btn) btn.innerText = '🎯 내 위치 찾기';
                        var gLat = pos.coords.latitude;
                        var gLng = pos.coords.longitude;
                        var acc = pos.coords.accuracy || 30;
                        // PC IP 위치 오차로 캠퍼스 반경(약 3km) 밖으로 크게 벗어난 경우 안내와 함께 실제 GPS 위치로 이동할지 표시
                        var distKm = Math.sqrt(Math.pow((gLat - 35.5438) * 111, 2) + Math.pow((gLng - 129.2563) * 88, 2));
                        if (distKm > 3.0 && !panToMe) {{
                            // 초기 자동 로드 시 PC IP 오차(타 지역)인 경우 캠퍼스 중심(학생회관)에 표시하되 안내 제공
                            renderMyLoc({my_init_lat}, {my_init_lng}, '내 현위치 (학생회관 기준)', 0);
                        }} else {{
                            renderMyLoc(gLat, gLng, '내 현위치 (GPS)', acc);
                            if (panToMe) map.setView([gLat, gLng], 17);
                        }}
                    }}, function(err) {{
                        if (btn) btn.innerText = '🎯 내 위치 찾기';
                        renderMyLoc({my_init_lat}, {my_init_lng}, myLocLabel, 0);
                        if (panToMe) map.setView([{my_init_lat}, {my_init_lng}], 17);
                    }}, {{enableHighAccuracy: true, timeout: 6000, maximumAge: 0}});
                }} else {{
                    renderMyLoc({my_init_lat}, {my_init_lng}, myLocLabel, 0);
                    if (panToMe) map.setView([{my_init_lat}, {my_init_lng}], 17);
                }}
            }}

            if (locConsent) {{
                // 초기 렌더링 시 즉시 핀을 생성하고(수동 지정 위치 또는 기본값), 자동 GPS 모드이면 실제 GPS로 갱신
                renderMyLoc({my_init_lat}, {my_init_lng}, myLocLabel, 0);
                if (useAutoGps) {{
                    findMyCampusLocation(false);
                }}
            }}

            if (!useAutoGps && locConsent) {{
                map.setView([{my_init_lat}, {my_init_lng}], 17);
            }} else if (latlngs.length === 1) {{
                map.setView(latlngs[0], 17);
            }} else if (latlngs.length > 1) {{
                map.fitBounds(latlngs, {{ padding: [45, 45], maxZoom: 17 }});
            }}
        </script>
    </body>
    </html>
    """, height=300)

    kakao_target = active_place_filter if active_place_filter else "울산대학교 학생회관"
    st.markdown(f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin:4px 0 12px 0;">
        <span style="font-size:12.5px; font-weight:700; color:#4E5968;">📍 핀을 클릭하면 모집 정보와 카카오맵 길찾기로 연결됩니다. (활성 <b>{total_active}건</b>)</span>
        {KakaoMapButton(kakao_target, "🗺️ 카카오맵 앱 열기")}
    </div>
    """, unsafe_allow_html=True)

    s_head1, s_head2 = st.columns([1.3, 1.4])
    with s_head1:
        st.markdown("#### 📌 주변 모집 글")
    with s_head2:
        map_sort_mode = st.selectbox(
            "정렬 기준",
            ["📍 내 위치에서 가까운 순", "🕒 최신 등록순"],
            index=0 if loc_consent else 1,
            label_visibility="collapsed",
            key="map_nearby_sort",
        )

    my_apps_map = {}
    my_apps_df = get_dataframe("SELECT post_id, status FROM applications WHERE applicant_id=?", (st.session_state.user_id,))
    for _, ar in my_apps_df.iterrows():
        my_apps_map[int(ar["post_id"])] = ar["status"]

    filtered_rows = []
    for _, row in map_posts.iterrows():
        norm_cat = normalize_category(row["category"])
        if map_cat != "전체" and norm_cat != map_cat:
            continue
        if active_place_filter and active_place_filter.lower() not in str(row["location"]).lower() and active_place_filter.lower() not in str(row["title"]).lower():
            continue
        p_lat, p_lng, _ = resolve_campus_location(row["location"])
        dist_m = calc_campus_distance_meters(my_init_lat, my_init_lng, p_lat, p_lng) if loc_consent else None
        filtered_rows.append((dist_m if dist_m is not None else 999999, row, dist_m))

    if map_sort_mode == "📍 내 위치에서 가까운 순" and loc_consent:
        filtered_rows.sort(key=lambda item: (item[0], -int(item[1]["id"])))

    shown = 0
    for _, row, dist_m in filtered_rows:
        acc_df = get_dataframe("SELECT count(*) as cnt FROM applications WHERE post_id=? AND status='승인됨'", (row["id"],))
        acc_cnt = int(acc_df.iloc[0]["cnt"]) if not acc_df.empty else 0
        MeetupCard(row, acc_cnt, my_apps_map.get(int(row["id"])), key_prefix="map", distance_m=dist_m)
        shown += 1

    if shown == 0:
        EmptyState("해당 위치/카테고리에 모집 중인 모임이 없습니다.")

# =========================================================
# 화면 E: 안심 채팅 화면 (SafeChat View)
# =========================================================
elif st.session_state.nav_tab == "채팅":
    execute_commit("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (st.session_state.user_id,))
    st.markdown("### 💬 안심 채팅 및 매칭 관리")

    # 1. 내가 방장인 모임 중 승인된 채팅 & 대기중 신청자
    my_hosted_apps = get_dataframe("""
        SELECT a.id as app_id, a.post_id, a.applicant_id, a.status,
               p.title, p.meet_date, p.meet_time, p.location, p.max_participants,
               u.nickname as partner_name, u.avatar as partner_avatar, u.manner_temp as partner_temp, u.mbti as partner_mbti
        FROM applications a
        JOIN posts p ON a.post_id = p.id
        JOIN users u ON a.applicant_id = u.student_id
        WHERE p.author_id = ?
        ORDER BY a.id DESC
    """, (st.session_state.user_id,))

    # 2. 내가 참여 신청한 모임
    my_applied = get_dataframe("""
        SELECT a.id as app_id, a.post_id, a.applicant_id, a.status,
               p.title, p.author_id, p.meet_date, p.meet_time, p.location, p.max_participants,
               u.nickname as partner_name, u.avatar as partner_avatar, u.manner_temp as partner_temp, u.mbti as partner_mbti
        FROM applications a
        JOIN posts p ON a.post_id = p.id
        JOIN users u ON p.author_id = u.student_id
        WHERE a.applicant_id = ?
        ORDER BY a.id DESC
    """, (st.session_state.user_id,))

    # 방장 수락 대기 중인 신청자 알림 섹션
    pending_host = my_hosted_apps[my_hosted_apps["status"] == "대기중"] if not my_hosted_apps.empty else pd.DataFrame()
    if not pending_host.empty:
        with st.container(border=True):
            st.markdown("#### 🔔 방장 수락 대기 중인 신청자")
            for _, prow in pending_host.iterrows():
                st.markdown(
                    f"**{prow['partner_avatar']} {prow['partner_name']}** ({prow['partner_mbti']} · 🌡️{prow['partner_temp']:.1f}°C) → 📌 **{prow['title']}**"
                )
                if st.button(f"✅ 수락하고 안심 채팅 열기", key=f"chat_accept_{prow['app_id']}", use_container_width=True, type="primary"):
                    execute_commit("UPDATE applications SET status='승인됨' WHERE id=?", (prow["app_id"],))
                    notify_user(prow["applicant_id"], f"[{prow['title']}] 신청이 수락되어 안심 채팅방이 열렸습니다!")
                    st.rerun()

    # 수락 대기 중인 내 신청 목록 (수락 전에는 채팅 잠금 상태 표시)
    pending_my = my_applied[my_applied["status"] == "대기중"] if not my_applied.empty else pd.DataFrame()
    if not pending_my.empty:
        for _, mrow in pending_my.iterrows():
            st.markdown(f"""
            <div class="uldaemo-card" style="background:#F7F8F4;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="privacy-pill-mini">🔒 방장 수락 대기중</span>
                    <span style="font-size:12px; color:#6B7684;">{mrow['meet_date']} {mrow['meet_time']}</span>
                </div>
                <div style="font-size:15px; font-weight:800; margin-top:6px;">{mrow['title']}</div>
                <div style="font-size:12px; color:#6B7684; margin-top:4px;">방장({mrow['partner_name']})이 수락하면 안심 채팅방이 자동으로 활성화됩니다.</div>
            </div>
            """, unsafe_allow_html=True)

    # 수락 완료(승인됨)된 활성 안심 채팅방 목록
    approved_host = my_hosted_apps[my_hosted_apps["status"] == "승인됨"] if not my_hosted_apps.empty else pd.DataFrame()
    approved_my = my_applied[my_applied["status"] == "승인됨"] if not my_applied.empty else pd.DataFrame()

    if approved_host.empty and approved_my.empty:
        EmptyState("열려 있는 안심 채팅방이 없습니다", "모집글에 참여 신청 후 방장이 수락하면 안전한 채팅방이 열립니다!")
    else:
        for _, crow in approved_host.iterrows():
            with st.container(border=True):
                render_chat(
                    crow["post_id"],
                    st.session_state.user_id,
                    crow["applicant_id"],
                    crow["partner_name"],
                    f"host_{crow['app_id']}",
                    post_meta=crow.to_dict(),
                )
                # 모임 완료 후 매너 평가
                rev_chk = get_dataframe(
                    "SELECT id FROM reviews WHERE post_id=? AND reviewer_id=? AND reviewee_id=?",
                    (crow["post_id"], st.session_state.user_id, crow["applicant_id"]),
                )
                if rev_chk.empty:
                    with st.expander(f"🏅 {crow['partner_name']}님 매너 평가 및 칭찬 스티커 남기기"):
                        rating = st.selectbox("만남 만족도", [5, 4, 3, 2, 1], key=f"rate_h_{crow['app_id']}")
                        kws = st.multiselect("칭찬 키워드 스티커", KW_OPTIONS, key=f"kw_h_{crow['app_id']}")
                        if st.button("평가 등록 완료", key=f"sub_rate_h_{crow['app_id']}", use_container_width=True, type="primary"):
                            apply_rating(crow["post_id"], st.session_state.user_id, crow["applicant_id"], rating, kws)
                            st.success("매너 온도와 칭찬 스티커가 반영되었습니다!")
                            st.rerun()
                else:
                    st.caption("✅ 이 학우에 대한 매너 평가를 완료했습니다.")

        for _, crow in approved_my.iterrows():
            with st.container(border=True):
                render_chat(
                    crow["post_id"],
                    st.session_state.user_id,
                    crow["author_id"],
                    crow["partner_name"],
                    f"guest_{crow['app_id']}",
                    post_meta=crow.to_dict(),
                )
                rev_chk = get_dataframe(
                    "SELECT id FROM reviews WHERE post_id=? AND reviewer_id=? AND reviewee_id=?",
                    (crow["post_id"], st.session_state.user_id, crow["author_id"]),
                )
                if rev_chk.empty:
                    with st.expander(f"🏅 방장 {crow['partner_name']}님 매너 평가 및 칭찬 스티커 남기기"):
                        rating = st.selectbox("만남 만족도", [5, 4, 3, 2, 1], key=f"rate_g_{crow['app_id']}")
                        kws = st.multiselect("칭찬 키워드 스티커", KW_OPTIONS, key=f"kw_g_{crow['app_id']}")
                        if st.button("평가 등록 완료", key=f"sub_rate_g_{crow['app_id']}", use_container_width=True, type="primary"):
                            apply_rating(crow["post_id"], st.session_state.user_id, crow["author_id"], rating, kws)
                            st.success("매너 온도와 칭찬 스티커가 반영되었습니다!")
                            st.rerun()
                else:
                    st.caption("✅ 방장에 대한 매너 평가를 완료했습니다.")

# =========================================================
# 화면 D: 프로필 화면 (Profile View - '마이' 탭)
# =========================================================
elif st.session_state.nav_tab == "마이":
    my_kws_df = get_dataframe(
        "SELECT keyword, count(*) as cnt FROM keyword_reviews WHERE reviewee_id=? GROUP BY keyword ORDER BY cnt DESC",
        (user["student_id"],),
    )
    praise_total = int(my_kws_df["cnt"].sum()) if not my_kws_df.empty else 28
    part_cnt_df = get_dataframe("SELECT count(*) as cnt FROM applications WHERE applicant_id=? AND status='승인됨'", (user["student_id"],))
    hosted_cnt_df = get_dataframe("SELECT count(*) as cnt FROM posts WHERE author_id=?", (user["student_id"],))
    total_join_cnt = int(part_cnt_df.iloc[0]["cnt"]) + int(hosted_cnt_df.iloc[0]["cnt"])
    if total_join_cnt == 0:
        total_join_cnt = 12  # 초기 예시 카운트

    kw_list = [f"{r['keyword']} ({r['cnt']})" for _, r in my_kws_df.iterrows()] if not my_kws_df.empty else ["시간 약속을 잘 지켜요 ⏰", "친절해요 😊", "적극적이에요 👍"]

    # 상단 프로필 요약 카드 (와이어프레임 4번 화면 그대로 구현)
    st.markdown(f"""
    <div class="uldaemo-card" style="text-align:center; padding:24px 18px;">
        <div style="width:76px; height:76px; border-radius:50%; background:#EEF8F3; border:2px solid #C5E6D6; margin:0 auto 10px auto; display:flex; align-items:center; justify-content:center; font-size:40px;">
            {user['avatar'].split()[0]}
        </div>
        <div style="font-size:20px; font-weight:800; color:#191F28;">
            {user['nickname']} <span style="color:#287D62;">✔</span>
        </div>
        <div style="font-size:13px; color:#6B7684; margin-top:2px; margin-bottom:14px;">
            {user['department']} · {user['mbti']}
        </div>
        {MannerTemperature(user['manner_temp'])}
        <div style="margin-top:10px;">
            {PraiseTag(kw_list[:3])}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 소개 & 주요 활동 & 참여 통계 카드
    bio_key = f"user_bio_{user['student_id']}"
    if bio_key not in st.session_state:
        st.session_state[bio_key] = "안녕하세요! 새로운 학우들과 다양한 활동을 해보고 싶어요. 같이 학식도 먹고, 카공도 하고, 운동도 해요! 😊"

    st.markdown(f"""
    <div class="uldaemo-card">
        <div style="font-size:14px; font-weight:800; color:#191F28; margin-bottom:6px;">소개</div>
        <div style="font-size:13px; color:#4E5968; line-height:1.5; margin-bottom:14px;">
            {st.session_state[bio_key]}
        </div>
        <div style="font-size:14px; font-weight:800; color:#191F28; margin-bottom:8px;">주요 활동</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px;">
            <span style="background:#FFF3E0; color:#E65100; padding:5px 12px; border-radius:999px; font-size:12px; font-weight:700;">🍚 밥약</span>
            <span style="background:#E8EAF6; color:#283593; padding:5px 12px; border-radius:999px; font-size:12px; font-weight:700;">💻 카공</span>
            <span style="background:#E0F2F1; color:#00695C; padding:5px 12px; border-radius:999px; font-size:12px; font-weight:700;">🏃 운동</span>
            <span style="background:#E8F5E9; color:#2E7D32; padding:5px 12px; border-radius:999px; font-size:12px; font-weight:700;">🚶 산책</span>
        </div>
        <div style="display:flex; gap:12px; text-align:center;">
            <div style="flex:1; background:#F7F8F4; border-radius:12px; padding:12px;">
                <div style="font-size:12px; color:#6B7684; font-weight:600;">모임 참여</div>
                <div style="font-size:20px; font-weight:800; color:#191F28; margin-top:2px;">{total_join_cnt}회</div>
            </div>
            <div style="flex:1; background:#F7F8F4; border-radius:12px; padding:12px;">
                <div style="font-size:12px; color:#6B7684; font-weight:600;">받은 칭찬</div>
                <div style="font-size:20px; font-weight:800; color:#287D62; margin-top:2px;">{praise_total}회</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 다른 이용자들이 남긴 칭찬 스티커 카드
    st.markdown(f"""
    <div class="uldaemo-card">
        <div style="font-size:14px; font-weight:800; color:#191F28; margin-bottom:8px;">다른 학우들이 남긴 칭찬 스티커</div>
        {PraiseTag(kw_list)}
    </div>
    """, unsafe_allow_html=True)

    # 프로필 수정 아코디언
    with st.expander("⚙️ 내 프로필 및 자기소개 수정하기 (프로필 필수 목록)", expanded=True):
        avatars_list = ["🐶 강아지", "🐱 고양이", "🦊 여우", "🐻 곰", "🐰 토끼", "🐹 햄스터"]
        mbti_list = ["ENFP", "ENTP", "INFP", "INTP", "ESFJ", "ESTJ", "ISFJ", "ISTJ", "ENFJ", "ENTJ", "INFJ", "INTJ", "ESFP", "ESTP", "ISFP", "ISTP", "모름/비공개"]
        new_nick = st.text_input("닉네임 변경 (필수)", value=user["nickname"], key="edit_prof_nick")
        new_dept = st.text_input("학과 변경 (필수)", value=user["department"], key="edit_prof_dept")
        new_avatar = st.selectbox("아바타 (필수)", avatars_list, index=avatars_list.index(user["avatar"]) if user["avatar"] in avatars_list else 0, key="edit_prof_avatar")
        new_mbti = st.selectbox("MBTI (필수)", mbti_list, index=mbti_list.index(user["mbti"]) if user["mbti"] in mbti_list else 0, key="edit_prof_mbti")
        new_bio = st.text_area("자기소개 한마디", value=st.session_state[bio_key], key="edit_prof_bio")

        if st.button("프로필 저장하기", key="save_my_profile_main", use_container_width=True, type="primary"):
            if not new_nick.strip() or not new_dept.strip():
                st.warning("닉네임과 학과(필수 항목)를 비워둘 수 없습니다.")
            else:
                execute_commit(
                    "UPDATE users SET nickname=?, department=?, avatar=?, mbti=? WHERE student_id=?",
                    (new_nick.strip(), new_dept.strip(), new_avatar, new_mbti, user["student_id"]),
                )
                st.session_state[bio_key] = new_bio.strip()
                st.success("프로필이 업데이트되었습니다!")
                st.rerun()

    if st.button("🚪 로그아웃", key="main_profile_logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_id = ""
        try:
            controller.remove("user_id")
        except Exception:
            pass
        st.rerun()
