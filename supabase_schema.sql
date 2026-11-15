-- ============================================================================
-- 울대모 (Uldaemo) Supabase PostgreSQL 스키마 (SQL Editor에 전체 복사 후 Run 클릭)
-- ============================================================================

-- 1. 학우(회원) 전용 테이블: Table Editor에서 엑셀처럼 한눈에 조회 및 직접 수정 가능
CREATE TABLE IF NOT EXISTS public.uldaemo_users (
    student_id TEXT PRIMARY KEY,                      -- 학번 (예: 20261275)
    nickname TEXT DEFAULT '',                         -- 닉네임
    department TEXT DEFAULT '울산대',                  -- 단과대 / 학과
    mbti TEXT DEFAULT '',                             -- MBTI
    manner_temp NUMERIC(5,2) DEFAULT 36.5,            -- 매너온도 (기본 36.5)
    report_count INTEGER DEFAULT 0,                   -- 누적 신고 횟수
    coffee_tickets INTEGER DEFAULT 0,                 -- ☕ 커피 응모권 수
    boost_coupons INTEGER DEFAULT 0,                  -- ⚡ 번개 상단 부스트권 수
    extra_post_coupons INTEGER DEFAULT 0,             -- ➕ 오늘 추가 개설권 수
    bonus_score INTEGER DEFAULT 0,                    -- 이달의 랭킹 보너스 점수
    streak_days INTEGER DEFAULT 1,                    -- 연속 출석 일수
    raw_data JSONB DEFAULT '{}'::jsonb,               -- 전체 프로필 원본 객체 (해시, 아바타, 관심태그 등)
    updated_at BIGINT DEFAULT 0,                      -- 클라이언트 갱신 시각 (ms)
    synced_at TIMESTAMPTZ DEFAULT now()               -- 서버 동기화 시각
);

-- 2. 번개 모임 게시글 테이블: 개설된 번개 모임을 행(Row) 단위로 조회 및 관리
CREATE TABLE IF NOT EXISTS public.uldaemo_posts (
    id BIGINT PRIMARY KEY,                            -- 번개 고유 ID
    author_id TEXT DEFAULT '',                        -- 방장 학번
    title TEXT DEFAULT '',                            -- 번개 제목
    category TEXT DEFAULT '',                         -- 카테고리 (🍚 밥약, ☕ 카공 등)
    location TEXT DEFAULT '',                         -- 모임 장소
    meet_date TEXT DEFAULT '',                        -- 모임 날짜 (YYYY-MM-DD)
    meet_time TEXT DEFAULT '',                        -- 모임 시간 (HH:MM)
    max_participants INTEGER DEFAULT 2,               -- 최대 모집 인원
    status TEXT DEFAULT '모집중',                      -- 상태 (모집중 / 매칭완료)
    is_official BOOLEAN DEFAULT false,                -- 운영진 공식 번개 여부
    raw_data JSONB DEFAULT '{}'::jsonb,               -- 전체 게시글 원본 객체
    updated_at BIGINT DEFAULT 0,                      -- 클라이언트 갱신 시각 (ms)
    synced_at TIMESTAMPTZ DEFAULT now()               -- 서버 동기화 시각
);

-- 3. 실시간 앱 통합 상태 스토어 (신청내역, 안심채팅, 알림, 매너칭찬, 투표, 광장톡 통합 보존)
CREATE TABLE IF NOT EXISTS public.uldaemo_state (
    id TEXT PRIMARY KEY,                              -- 'main' 고정 키
    data JSONB DEFAULT '{}'::jsonb,                   -- 전체 스토어 JSONB
    updated_at BIGINT DEFAULT 0,                      -- 갱신 시각 (ms)
    synced_at TIMESTAMPTZ DEFAULT now()               -- 서버 동기화 시각
);

-- 4. 인덱스 생성 (조회 성능 최적화)
CREATE INDEX IF NOT EXISTS idx_uldaemo_users_temp ON public.uldaemo_users (manner_temp DESC);
CREATE INDEX IF NOT EXISTS idx_uldaemo_posts_date ON public.uldaemo_posts (meet_date DESC, id DESC);

-- 5. RLS(Row Level Security) 설정 및 서버 API 접근 허용 정책
ALTER TABLE public.uldaemo_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uldaemo_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uldaemo_state ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "uldaemo_users_api_policy" ON public.uldaemo_users;
CREATE POLICY "uldaemo_users_api_policy" ON public.uldaemo_users
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "uldaemo_posts_api_policy" ON public.uldaemo_posts;
CREATE POLICY "uldaemo_posts_api_policy" ON public.uldaemo_posts
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "uldaemo_state_api_policy" ON public.uldaemo_state;
CREATE POLICY "uldaemo_state_api_policy" ON public.uldaemo_state
    FOR ALL USING (true) WITH CHECK (true);
