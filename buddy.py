import streamlit as st
import pandas as pd
import psycopg2
import os
import urllib.parse
from datetime import datetime, date, timedelta
import requests
import json

# AI 헬퍼 함수 (REST API 기반 - 빠르고 안정적)
def call_gemini(prompt):
    try:
        api_key = st.secrets["gemini"]["api_key"]
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=5)
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        pass
    return ""

# =========================================================
# 1. 데이터베이스 헬퍼 함수
# =========================================================
def get_connection():
    return psycopg2.connect(st.secrets["supabase"]["url"])

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        student_id TEXT PRIMARY KEY, email TEXT, is_verified INTEGER DEFAULT 0,
        nickname TEXT, avatar TEXT, gender TEXT, department TEXT, mbti TEXT,
        manner_temp REAL DEFAULT 36.5, report_count INTEGER DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY, author_id TEXT, title TEXT, category TEXT,
        meet_date TEXT, meet_time TEXT, location TEXT, max_participants INTEGER DEFAULT 1,
        meeting_style TEXT, status TEXT DEFAULT '모집중'
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        id SERIAL PRIMARY KEY, post_id INTEGER, applicant_id TEXT, status TEXT DEFAULT '대기중'
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id SERIAL PRIMARY KEY, post_id INTEGER, reviewer_id TEXT, reviewee_id TEXT,
        rating INTEGER, is_noshow INTEGER DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS keyword_reviews (
        id SERIAL PRIMARY KEY, post_id INTEGER, reviewer_id TEXT, reviewee_id TEXT,
        keyword TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY, post_id INTEGER, sender_id TEXT, text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id SERIAL PRIMARY KEY, reporter_id TEXT, reported_id TEXT, reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY, user_id TEXT, message TEXT, is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def get_dataframe(query, params=()):
    conn = get_connection()
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
    query = query.replace("?", "%s")
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def notify_user(user_id, message):
    execute_commit("INSERT INTO notifications (user_id, message) VALUES (?, ?)", (user_id, message))

init_db()

# =========================================================
# 2. 비즈니스 로직 헬퍼 함수
# =========================================================
def apply_rating(post_id, reviewer_id, reviewee_id, rating, keywords):
    execute_commit("INSERT INTO reviews (post_id, reviewer_id, reviewee_id, rating) VALUES (?, ?, ?, ?)", 
                   (post_id, reviewer_id, reviewee_id, rating))
    temp_change = {5: 0.5, 4: 0.2, 3: 0.0, 2: -0.5, 1: -1.0}.get(rating, 0)
    execute_commit("UPDATE users SET manner_temp = manner_temp + ? WHERE student_id = ?", (temp_change, reviewee_id))
    
    for kw in keywords:
        execute_commit("INSERT INTO keyword_reviews (post_id, reviewer_id, reviewee_id, keyword) VALUES (?, ?, ?, ?)", 
                       (post_id, reviewer_id, reviewee_id, kw))

def apply_noshow(post_id, reporter_id, reported_id):
    execute_commit("INSERT INTO reviews (post_id, reviewer_id, reviewee_id, rating, is_noshow) VALUES (?, ?, ?, 1, 1)", 
                   (post_id, reporter_id, reported_id))
    execute_commit("INSERT INTO reports (reporter_id, reported_id, reason) VALUES (?, ?, '노쇼')", 
                   (reporter_id, reported_id))
    execute_commit("UPDATE users SET manner_temp = manner_temp - 5.0, report_count = report_count + 1 WHERE student_id = ?", 
                   (reported_id,))

# =========================================================
# 3. UI 컴포넌트 헬퍼 함수
# =========================================================
def render_chat(post_id, my_id, other_id, other_name, unique_suffix):
    st.markdown("---")
    st.subheader(f"💬 {other_name}님과의 안심 채팅방")
    msgs = get_dataframe("SELECT sender_id, text, created_at FROM messages WHERE post_id=? ORDER BY id ASC", (post_id,))
    
    # [수정 3] 새 메시지 알림음 (띠링~)
    chat_key = f"chat_count_{post_id}_{other_id}_{unique_suffix}"
    current_len = len(msgs)
    if chat_key not in st.session_state:
        st.session_state[chat_key] = current_len
        
    if current_len > st.session_state[chat_key]:
        last_msg = msgs.iloc[-1]
        if last_msg["sender_id"] != my_id:
            # 구글 공식 알림음 재생 (화면에 보이지 않음)
            st.components.v1.html("""
                <audio autoplay>
                    <source src="https://actions.google.com/sounds/v1/alarms/beep_short.ogg" type="audio/ogg">
                </audio>
            """, height=0)
        st.session_state[chat_key] = current_len
    
    chat_container = st.container(height=300)
    for _, msg in msgs.iterrows():
        if msg["sender_id"] == my_id:
            chat_container.chat_message("user").write(msg["text"])
        elif msg["sender_id"] == "AI_BOT":
            chat_container.chat_message("ai").write(msg["text"])
        else:
            chat_container.chat_message("assistant").write(msg["text"])
            
    col1, col2 = st.columns([5,1])
    new_msg = col1.text_input("메시지 입력", key=f"msg_input_{post_id}_{other_id}_{unique_suffix}", label_visibility="collapsed")
    if col2.button("전송", key=f"send_btn_{post_id}_{other_id}_{unique_suffix}"):
        if new_msg.strip():
            # 🛡️ 안심 AI 경찰 기능
            with st.spinner("경찰 AI가 메시지를 검사 중입니다... 🚓"):
                prompt = f"다음 메시지에 심한 욕설, 성적 발언, 또는 '카톡', '전번', '번호', '라인', '인스타' 등 사적인 연락처를 요구하는 내용이 있다면 '경고', 평범한 대화라면 '통과'라고만 대답해. 메시지: {new_msg}"
                resp = call_gemini(prompt).strip()
                if '경고' in resp:
                    st.error("🚨 [안심 AI 경찰] 부적절한 언행 또는 외부 연락처 요구가 감지되어 메시지 전송이 차단되었습니다.")
                    st.stop()
            execute_commit("INSERT INTO messages (post_id, sender_id, text) VALUES (?, ?, ?)", (post_id, my_id, new_msg))
            st.rerun()
            
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 채팅 새로고침", key=f"refresh_{post_id}_{other_id}_{unique_suffix}"):
            st.rerun()
    with c2:
        if st.button("🤖 AI 비서 호출 (대화주제 & 맛집)", key=f"ai_btn_{post_id}_{other_id}_{unique_suffix}"):
            with st.spinner("AI 비서가 추천을 작성하고 있습니다... 💡"):
                post_info = get_dataframe("SELECT category, location, meeting_style FROM posts WHERE id=?", (post_id,)).iloc[0]
                prompt = f"대학생 두 명이 현재 '{post_info['location']}'에서 '{post_info['category']}' 목적으로 만나는 중이야. 둘의 만남 성향은 '{post_info['meeting_style']}'이야. 어색함을 깰 수 있는 재미있는 대화 소재 1가지와, 근처 맛집이나 놀거리 1가지를 3~4줄로 발랄하게 추천해줘."
                ai_reply = call_gemini(prompt)
                if ai_reply:
                    execute_commit("INSERT INTO messages (post_id, sender_id, text) VALUES (?, ?, ?)", (post_id, "AI_BOT", f"**[🤖 AI 비서 추천]**\n{ai_reply}"))
                    st.rerun()
                else:
                    st.error("AI 비서 서버와 연결이 지연되고 있습니다. 나중에 다시 시도해 주세요.")

def render_sidebar_profile(user):
    st.sidebar.header("👤 내 프로필")
    st.sidebar.markdown(f"## {user['avatar']}")
    st.sidebar.markdown(f"**닉네임:** {user['nickname']}")
    st.sidebar.markdown(f"**학과:** {user['department']} | **MBTI:** {user['mbti']}")
    
    badge = "✅" if user['manner_temp'] >= 40.0 else ""
    st.sidebar.subheader("🌡️ 나의 매너 온도")
    if user['manner_temp'] >= 40.0:
        st.sidebar.success(f"**{user['manner_temp']:.1f} °C** {badge}\n\n모범 학우입니다!")
    elif user['manner_temp'] <= 30.0:
        st.sidebar.error(f"**{user['manner_temp']:.1f} °C**\n\n주의: 온도가 낮습니다.")
    else:
        st.sidebar.info(f"**{user['manner_temp']:.1f} °C**\n\n첫 온도 36.5도에서 시작합니다.")
        
    kws = get_dataframe("SELECT keyword, count(*) as cnt FROM keyword_reviews WHERE reviewee_id=? GROUP BY keyword ORDER BY cnt DESC LIMIT 3", (user["student_id"],))
    if not kws.empty:
        st.sidebar.markdown("**💖 받은 칭찬 배지**")
        for _, r in kws.iterrows():
            st.sidebar.caption(f"{r['keyword']} (x{r['cnt']})")
            
    # [수정 2] 프로필 수정 기능 추가
    with st.sidebar.expander("⚙️ 내 프로필 수정"):
        avatars_list = ["🐶 강아지", "🐱 고양이", "🦊 여우", "🐻 곰", "🐰 토끼", "🐹 햄스터"]
        mbti_list = ["모름/비공개", "ENFP", "ENTP", "INFP", "INTP", "ESFJ", "ESTJ", "ISFJ", "ISTJ", "ENFJ", "ENTJ", "INFJ", "INTJ", "ESFP", "ESTP", "ISFP", "ISTP"]
        
        new_nick = st.text_input(f"새 닉네임 (기존: {user['nickname']})", placeholder="변경할 닉네임을 입력하세요")
        new_avatar = st.selectbox("아바타", avatars_list, index=avatars_list.index(user["avatar"]) if user["avatar"] in avatars_list else 0)
        new_mbti = st.selectbox("MBTI", mbti_list, index=mbti_list.index(user["mbti"]) if user["mbti"] in mbti_list else 0)
        
        if st.button("저장하기", key="save_profile"):
            final_nick = new_nick.strip() if new_nick.strip() != "" else user["nickname"]
            execute_commit("UPDATE users SET nickname=?, avatar=?, mbti=? WHERE student_id=?", 
                           (final_nick, new_avatar, new_mbti, user["student_id"]))
            st.success("프로필이 수정되었습니다!")
            st.rerun()
        
    unreads = get_dataframe("SELECT count(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0", (st.session_state.user_id,))
    unread_cnt = unreads.iloc[0]["cnt"]
    if unread_cnt > 0:
        st.sidebar.warning(f"🔔 새 알림이 {unread_cnt}개 있습니다! (내 매칭 탭 확인)")
    
    if st.sidebar.button("로그아웃"):
        st.session_state.logged_in = False
        st.session_state.user_id = ""
        st.session_state.verified_email = None
        try:
            controller.remove('user_id')
        except:
            pass
        st.rerun()

# =========================================================
# 4. 앱 초기 설정 및 인증 (쿠키 적용)
# =========================================================
st.set_page_config(page_title="울대모 - 울산대생 다 모여라", page_icon="⚡", layout="centered")

from streamlit_cookies_controller import CookieController
controller = CookieController()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""

# 브라우저 쿠키에 user_id가 있으면 자동 로그인 (수정 4 유지)
try:
    stored_user_id = controller.get('user_id')
except TypeError:
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
        st.success(f"✅ 인증 완료: {st.session_state.verified_email}")
        return st.session_state.verified_email
        
    st.subheader("🔒 대학 웹메일 인증 (임시)")
    email = st.text_input("학교 웹메일 (예: user@ulsan.ac.kr)")
    
    if st.button("인증번호 발송"):
        if email.endswith(".ac.kr"):
            st.session_state.auth_code_sent = True
            st.success("인증번호 '123456'이 발송되었습니다. (가상 발송)")
        else:
            st.error("반드시 .ac.kr 로 끝나는 학교 웹메일을 입력해주세요.")
            
    if st.session_state.auth_code_sent:
        code = st.text_input("인증번호 6자리 입력")
        if st.button("인증 확인"):
            if code == "123456":
                st.session_state.verified_email = email
                st.rerun()
            else:
                st.error("인증번호가 틀렸습니다.")
    return None

st.title("⚡ 울대모 (울산대생 다 모여라)")
st.caption("밥약, 카공, 산책, 코노까지! 검증된 학우들과 안전하고 건전하게 만나세요.")

if not st.session_state.logged_in:
    st.header("로그인 및 프로필 설정")
    user_student_id = st.text_input("학번 (아이디로 사용)", placeholder="예: 20240001")
    verified_email = verify_email()
    
    if verified_email and user_student_id:
        st.subheader("👤 기본 프로필 입력 (블라인드)")
        user_nickname = st.text_input("닉네임 (실명 비공개)")
        user_avatar = st.selectbox("내 아바타", ["🐶 강아지", "🐱 고양이", "🦊 여우", "🐻 곰", "🐰 토끼", "🐹 햄스터"])
        user_gender = st.selectbox("성별", ["남성", "여성"])
        user_dept = st.text_input("학과", value="컴퓨터공학과")
        user_mbti = st.selectbox("MBTI", ["모름/비공개", "ENFP", "ENTP", "INFP", "INTP", "ESFJ", "ESTJ", "ISFJ", "ISTJ", "ENFJ", "ENTJ", "INFJ", "INTJ", "ESFP", "ESTP", "ISFP", "ISTP"])
        
        if st.button("가입 및 로그인"):
            if user_nickname.strip() == "":
                st.warning("닉네임을 입력해주세요.")
            else:
                execute_commit("""
                    INSERT INTO users (student_id, email, is_verified, nickname, avatar, gender, department, mbti)
                    VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                    ON CONFLICT(student_id) DO UPDATE SET 
                    email=?, nickname=?, avatar=?, gender=?, department=?, mbti=?
                """, (user_student_id, verified_email, user_nickname, user_avatar, user_gender, user_dept, user_mbti,
                      verified_email, user_nickname, user_avatar, user_gender, user_dept, user_mbti))
                st.session_state.logged_in = True
                st.session_state.user_id = user_student_id
                controller.set('user_id', user_student_id)
                st.rerun()
    st.stop()

# =========================================================
# 5. 메인 화면 렌더링
# =========================================================
user_info = get_dataframe("SELECT * FROM users WHERE student_id = ?", (st.session_state.user_id,))
if not user_info.empty:
    user = user_info.iloc[0]
    if user["report_count"] >= 3:
        st.error("🚨 누적 신고 3회 이상으로 계정이 정지되었습니다. 관리자에게 문의하세요.")
        st.stop()
        
    render_sidebar_profile(user)

tab1, tab2, tab3 = st.tabs(["🔍 실시간 번개 찾기", "✍️ 번개 파티 만들기", "💬 내 매칭 & 안심 채팅"])
now = datetime.now()

# ---------------------------------------------------------
# TAB 1: 실시간 번개 찾기
# ---------------------------------------------------------
with tab1:
    hotspot = get_dataframe("SELECT location, count(*) as cnt FROM posts WHERE status='모집중' GROUP BY location ORDER BY cnt DESC LIMIT 1")
    if not hotspot.empty and hotspot.iloc[0]['cnt'] > 0:
        loc = hotspot.iloc[0]['location']
        cnt = hotspot.iloc[0]['cnt']
        st.error(f"🔥 **캠퍼스 핫스팟 레이더:** 현재 **{loc}**에서 {cnt}개의 번개가 모집 중입니다!")
        st.divider()

    col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
    with col_s1:
        search_kw = st.text_input("🔍 검색", placeholder="예: 마라탕, 볼링, 학생회관", label_visibility="collapsed")
    with col_s2:
        filter_date = st.selectbox("📅 날짜", ["모든 날짜", "오늘 만남만"], label_visibility="collapsed")
    with col_s3:
        filter_category = st.selectbox("🏷️ 카테고리", ["전체", "🍚 밥약/식사", "☕ 카공/스터디", "🎮 PC방/게임", "🎤 코노/취미", "✨ 기타"], label_visibility="collapsed")
        
    query = """
        SELECT p.id, p.title, p.category, p.meet_date, p.meet_time, p.location, p.max_participants, p.meeting_style, p.status, p.author_id,
               u.nickname, u.avatar, u.manner_temp, u.mbti
        FROM posts p JOIN users u ON p.author_id = u.student_id WHERE p.status = '모집중'
    """
    if filter_category == "✨ 기타":
        query += " AND p.category NOT IN ('🍚 밥약/식사', '☕ 카공/스터디', '🎮 PC방/게임', '🎤 코노/취미')"
    elif filter_category != "전체":
        query += f" AND p.category = '{filter_category}'"
        
    if filter_date == "오늘 만남만":
        today_str = date.today().strftime("%Y-%m-%d")
        query += f" AND p.meet_date = '{today_str}'"
        
    if search_kw.strip():
        kw = search_kw.strip()
        query += f" AND (p.title LIKE '%{kw}%' OR p.location LIKE '%{kw}%' OR p.meeting_style LIKE '%{kw}%')"
        
    query += " ORDER BY p.meet_date ASC, p.meet_time ASC"
    
    posts_df = get_dataframe(query)

    if posts_df.empty:
        st.info("현재 모집 중인 번개가 없습니다. 직접 만들어 보세요!")
    else:
        for _, row in posts_df.iterrows():
            post_datetime = datetime.strptime(f"{row['meet_date']} {row['meet_time']}", "%Y-%m-%d %H:%M")
            
            # [수정 3] 만료 시간 유예 (약속 시간 기준 +1시간 뒤에 자동 만료)
            if post_datetime + timedelta(hours=1) < now:
                execute_commit("UPDATE posts SET status='만료됨' WHERE id=?", (row['id'],))
                continue
                
            accepted = get_dataframe("SELECT count(*) as cnt FROM applications WHERE post_id=? AND status='승인됨'", (row['id'],)).iloc[0]["cnt"]
            pbadge = "✅" if row['manner_temp'] >= 40.0 else ""
            
            # [수정] 내가 만든 모임은 한눈에 띄게 표시
            my_tag = "⭐[내 모임] " if row["author_id"] == st.session_state.user_id else ""
            
            with st.expander(f"{my_tag}[{row['category']}] {row['title']} - {row['meet_date']} {row['meet_time']} ({accepted}/{row['max_participants']}명)"):
                st.markdown(f"**방장 프로필:** {row['avatar']} {row['nickname']} (🌡️ {row['manner_temp']}°C) {pbadge} | MBTI: {row['mbti']}")
                
                # [수정 1] 카카오맵 연동 (울산대 기준)
                search_loc = row['location']
                if "호관 " in search_loc:
                    search_loc = search_loc.split("호관 ", 1)[1]  # "1호관 화학공학관" -> "화학공학관"만 추출
                map_query = urllib.parse.quote(f"울산대학교 {search_loc}")
                st.markdown(f"📍 **장소:** {row['location']} &nbsp; [📌 카카오맵으로 정확한 위치 보기](https://map.kakao.com/link/search/{map_query})")
                st.markdown(f"**🏷️ 만남 성향:** `{row['meeting_style']}`")
                
                if row["author_id"] == st.session_state.user_id:
                    st.caption("내가 작성한 모집글입니다. '내 매칭 관리'에서 확인하세요.")
                elif accepted >= row['max_participants']:
                    st.error("정원이 마감되었습니다.")
                else:
                    if st.button("신청하기 (안심 매칭)", key=f"apply_{row['id']}"):
                        check = get_dataframe("SELECT * FROM applications WHERE post_id=? AND applicant_id=?", (row["id"], st.session_state.user_id))
                        if not check.empty:
                            st.warning("이미 신청한 번개입니다.")
                        else:
                            execute_commit("INSERT INTO applications (post_id, applicant_id) VALUES (?, ?)", (row["id"], st.session_state.user_id))
                            st.success("신청 완료! 방장이 수락하면 '안심 채팅'이 열립니다.")
                            notify_user(row["author_id"], f"[{row['title']}] 글에 {user['nickname']}님이 신청했습니다!")

# ---------------------------------------------------------
# TAB 2: 번개 파티 만들기
# ---------------------------------------------------------
with tab2:
    with st.form("create_post_form"):
        title = st.text_input("제목", placeholder="예: 오늘 3시 정문 앞 코노 가실 분!")
        
        category_preset = st.selectbox("카테고리", ["🍚 밥약/식사", "☕ 카공/스터디", "🎮 PC방/게임", "🎤 코노/취미", "✨ 기타 (직접 입력)"])
        if category_preset == "✨ 기타 (직접 입력)":
            category = st.text_input("카테고리 직접 입력", placeholder="예: ⚽ 축구, 🎬 영화, 🚶 산책")
        else:
            category = category_preset
            
        c1, c2 = st.columns(2)
        with c1:
            meet_date = st.date_input("약속 날짜", min_value=date.today())
            meet_time = st.time_input("약속 시간", now.time())
            max_participants = st.number_input("모집 인원 (본인 제외)", min_value=1, max_value=10, value=1)
        with c2:
            ulsan_univ_buildings = [
                "직접 입력",
                "1호관 화학공학관", "2호관 기계항공관", "3호관 공학행정관", "4호관 학생회관별관", "5호관 산학협력리더스홀",
                "6호관 조형관", "7호관 전기/컴퓨터공학관", "8호관 자연과학관", "9호관 대학회관/해송홀", "10호관 문수관",
                "11호관 교수연구동", "12호관 체육관", "13호관 동아리관 I", "14호관 인문관", "15호관 사회과학관",
                "16호관 아산도서관", "18호관 재료/산업공학관", "19호관 기초과학실험동", "20호관 시청각교육관",
                "21호관 학군단", "22호관 학생회관", "23호관 건설환경공학관", "24호관 경영관", 
                "25호관 청운학사 무거관", "26호관 행정본관", "27호관 해양공학수조", "28호관 예술관(디자인/미술)", 
                "29호관 예술관(음악)", "30호관 공장실험동", "31호관 동아리관 II", "32호관 조소실습동", 
                "33호관 청운학사 문수관", "34호관 식물원", "35호관 산학협동관", "36호관 서점 및 북카페", 
                "37호관 생활과학관", "38호관 청운학사 목련관", "39호관 아산스포츠센터", "40호관 아산도서관 신관",
                "41호관 조선해양공학관", "42호관 조선해양항공학시험동", "43호관 국제관", "44호관 건축관", 
                "45호관 청운학사 기린관", "46호관 KCC생활관", "99호관 과학대 9호관",
                "바보사거리 앞", "정문 앞", "후문 앞"
            ]
            location_preset = st.selectbox("만날 장소 (울산대 전체 건물)", ulsan_univ_buildings)
            location = st.text_input("직접 입력", placeholder="예: 정문 앞 스타벅스") if location_preset == "직접 입력" else location_preset
            meeting_style = st.selectbox("만남 성향", ["이어폰 꽂고 조용히 각자 할일", "간단한 스몰토크 환영", "텐션 높게 E처럼 놀아요", "정보 공유 및 진지한 대화"])

        if st.form_submit_button("🚀 번개 파티 열기"):
            if not title.strip() or not location.strip():
                st.error("제목과 장소를 모두 입력해주세요.")
            else:
                execute_commit("""
                    INSERT INTO posts (author_id, title, category, meet_date, meet_time, location, max_participants, meeting_style)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (st.session_state.user_id, title, category, meet_date.strftime("%Y-%m-%d"), meet_time.strftime("%H:%M"), location, max_participants, meeting_style))
                st.success("등록 완료! '번개 찾기' 목록에서 확인하세요.")

# ---------------------------------------------------------
# TAB 3: 내 매칭 관리 & 안심 채팅
# ---------------------------------------------------------
with tab3:
    execute_commit("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (st.session_state.user_id,))
    KW_OPTIONS = ["시간 약속을 잘 지켜요 ⏰", "리액션이 엄청나요 👏", "밥/커피를 사주셨어요 👼", "대화가 잘 통해요 💬", "조용히 집중하기 좋아요 📚"]

    st.header("내가 만든 파티 관리")
    my_posts = get_dataframe("SELECT * FROM posts WHERE author_id = ? ORDER BY id DESC", (st.session_state.user_id,))
    for _, post in my_posts.iterrows():
        # [수정 4] 24시간 지난 과거 파티는 자연스럽게 숨김 처리
        post_dt = datetime.strptime(f"{post['meet_date']} {post['meet_time']}", "%Y-%m-%d %H:%M")
        if post["status"] in ["취소됨", "만료됨", "매칭완료"] and post_dt + timedelta(hours=24) < now:
            continue
            
        with st.container(border=True):
            st.markdown(f"#### 📌 {post['title']} (`{post['status']}`)")
            
            # [수정 1] 카카오맵 연동
            search_loc = post['location']
            if "호관 " in search_loc:
                search_loc = search_loc.split("호관 ", 1)[1]
            map_query = urllib.parse.quote(f"울산대학교 {search_loc}")
            st.markdown(f"📍 **약속 장소:** {post['location']} &nbsp; [📌 카카오맵으로 위치 보기](https://map.kakao.com/link/search/{map_query})")
            
            if post["status"] in ["모집중", "매칭완료"]:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🚫 이 모임 취소하기 (방폭)", key=f"cancel_post_{post['id']}"):
                        execute_commit("UPDATE posts SET status='취소됨' WHERE id=?", (post["id"],))
                        apps = get_dataframe("SELECT applicant_id FROM applications WHERE post_id=?", (post["id"],))
                        for _, app_row in apps.iterrows():
                            notify_user(app_row["applicant_id"], f"방장이 [{post['title']}] 모임을 취소했습니다.")
                            execute_commit("UPDATE applications SET status='방장취소' WHERE post_id=? AND applicant_id=?", (post["id"], app_row["applicant_id"]))
                        st.rerun()
                with col_btn2:
                    # [수정 3] 방장의 모집 조기 마감 기능
                    if st.button("🔒 모집 조기 마감 (더 이상 안 받기)", key=f"early_close_{post['id']}"):
                        execute_commit("UPDATE posts SET status='매칭완료' WHERE id=?", (post["id"],))
                        st.rerun()
            
            apps = get_dataframe("""
                SELECT a.id as app_id, a.applicant_id, u.nickname, u.mbti, u.manner_temp, a.status
                FROM applications a JOIN users u ON a.applicant_id = u.student_id WHERE a.post_id = ?
            """, (post["id"],))
            
            accepted_count = len(apps[apps["status"] == "승인됨"])
            for _, app in apps.iterrows():
                badge_str = "✅" if app['manner_temp'] >= 40.0 else ""
                st.write(f"- {app['nickname']} ({app['mbti']} / 🌡️{app['manner_temp']}°C) {badge_str} - [{app['status']}]")
                
                if post["status"] == "모집중" and app["status"] == "대기중":
                    if accepted_count < post["max_participants"]:
                        if st.button("수락하기", key=f"accept_{app['app_id']}"):
                            execute_commit("UPDATE applications SET status='승인됨' WHERE id=?", (app["app_id"],))
                            notify_user(app["applicant_id"], f"[{post['title']}] 글 신청이 수락되었습니다!")
                            if accepted_count + 1 >= post["max_participants"]:
                                execute_commit("UPDATE posts SET status='매칭완료' WHERE id=?", (post["id"],))
                            st.rerun()
                    else:
                        st.warning("정원이 초과되어 수락할 수 없습니다.")
                
                if app["status"] == "승인됨":
                    render_chat(post["id"], st.session_state.user_id, app["applicant_id"], app["nickname"], f"host_{app['app_id']}")
                    if get_dataframe("SELECT id FROM reviews WHERE post_id=? AND reviewer_id=? AND reviewee_id=?", (post["id"], st.session_state.user_id, app["applicant_id"])).empty:
                        with st.form(key=f"review_form_{app['applicant_id']}"):
                            st.write("상대방에 대한 평가를 남겨주세요!")
                            rating = st.selectbox("만남 평가 (별점)", [5, 4, 3, 2, 1])
                            selected_kws = st.multiselect("칭찬 키워드 스티커 (다중 선택 가능)", KW_OPTIONS)
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.form_submit_button("평가 남기기"):
                                    apply_rating(post["id"], st.session_state.user_id, app["applicant_id"], rating, selected_kws)
                                    st.rerun()
                            with col2:
                                if st.form_submit_button("🚨 노쇼 신고하기"):
                                    apply_noshow(post["id"], st.session_state.user_id, app["applicant_id"])
                                    st.rerun()
                    else:
                        st.caption("✅ 평가를 완료했습니다.")

    st.divider()
    st.header("내가 참여 중인 파티")
    my_apps = get_dataframe("""
        SELECT p.id as post_id, p.title, p.author_id, p.location, p.meet_date, p.meet_time, u.nickname as author_name, a.status, a.id as app_id
        FROM applications a JOIN posts p ON a.post_id = p.id JOIN users u ON p.author_id = u.student_id
        WHERE a.applicant_id = ? ORDER BY p.id DESC
    """, (st.session_state.user_id,))

    for _, app in my_apps.iterrows():
        # [수정 4] 24시간 지난 과거 파티는 자연스럽게 숨김 처리
        app_dt = datetime.strptime(f"{app['meet_date']} {app['meet_time']}", "%Y-%m-%d %H:%M")
        if app_dt + timedelta(hours=24) < now:
            continue
            
        with st.container(border=True):
            st.write(f"#### **{app['title']}** (방장: {app['author_name']})")
            st.write(f"- 상태: `{app['status']}`")
            
            if app['status'] == "대기중" and st.button("신청 취소", key=f"cancel_app_{app['app_id']}"):
                execute_commit("UPDATE applications SET status='신청취소' WHERE id=?", (app["app_id"],))
                notify_user(app["author_id"], f"[{app['title']}] 신청이 취소되었습니다.")
                st.rerun()
                    
            if app['status'] == "승인됨":
                # [수정 1] 카카오맵 연동
                search_loc = app['location']
                if "호관 " in search_loc:
                    search_loc = search_loc.split("호관 ", 1)[1]
                map_query = urllib.parse.quote(f"울산대학교 {search_loc}")
                st.markdown(f"📍 **약속 장소:** {app['location']} &nbsp; [📌 카카오맵으로 위치 보기](https://map.kakao.com/link/search/{map_query})")
                
                render_chat(app["post_id"], st.session_state.user_id, app["author_id"], app["author_name"], f"app_{app['app_id']}")
                
                if get_dataframe("SELECT id FROM reviews WHERE post_id=? AND reviewer_id=? AND reviewee_id=?", (app["post_id"], st.session_state.user_id, app["author_id"])).empty:
                    with st.form(key=f"review_form_author_{app['post_id']}"):
                        st.write("방장에 대한 평가를 남겨주세요!")
                        rating = st.selectbox("방장 평가 (별점)", [5, 4, 3, 2, 1])
                        selected_kws = st.multiselect("칭찬 키워드 스티커 (다중 선택 가능)", KW_OPTIONS)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("평가 남기기"):
                                apply_rating(app["post_id"], st.session_state.user_id, app["author_id"], rating, selected_kws)
                                st.rerun()
                        with col2:
                            if st.form_submit_button("🚨 노쇼 신고하기"):
                                apply_noshow(app["post_id"], st.session_state.user_id, app["author_id"])
                                st.rerun()
                else:
                    st.caption("✅ 평가를 완료했습니다.")
