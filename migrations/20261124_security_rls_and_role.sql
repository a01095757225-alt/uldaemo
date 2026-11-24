-- ============================================================================
-- 울대모 (Uldaemo) 보안 강화 마이그레이션 및 Supabase RLS 정책 초안
-- 작성일: 2026-11-24 | 브랜치: security/backend-auth-overhaul
-- 주의: 운영 DB에 자동 적용하지 않으며, 관리자 확인 후 Supabase SQL Editor에서 실행하세요.
-- ============================================================================

-- 1. uldaemo_users 테이블에 서버 권한 판별용 role 컬럼 추가
ALTER TABLE public.uldaemo_users
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uldaemo_users_role_check'
    ) THEN
        ALTER TABLE public.uldaemo_users
            ADD CONSTRAINT uldaemo_users_role_check CHECK (role IN ('user', 'admin'));
    END IF;
END $$;

-- 2. 기존 운영진 계정에 admin 역할 부여 (실행 전 실제 운영진 학번으로 치환하세요)
-- UPDATE public.uldaemo_users
--    SET role = 'admin',
--        raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{role}', '"admin"', true)
--  WHERE student_id = '<ADMIN_STUDENT_ID>';

-- 3. 역할 조회 성능용 인덱스
CREATE INDEX IF NOT EXISTS idx_uldaemo_users_role ON public.uldaemo_users (role);

-- ============================================================================
-- 4. Supabase RLS(Row Level Security) 강화 정책
--    - 기존 USING (true) WITH CHECK (true) 정책은 anon/authenticated 키로
--      전체 테이블을 읽고 쓸 수 있는 치명적 취약점이므로 즉시 폐기합니다.
--    - 모든 클라이언트는 Vercel 서버리스 API(/api/index)를 통해서만 접근하며,
--      서버 API는 Vercel 환경변수 SUPABASE_SERVICE_ROLE_KEY(RLS 우회)만 사용합니다.
--    - 따라서 anon / authenticated 역할에 대해서는 모든 테이블 접근을 전면 차단합니다.
-- ============================================================================

ALTER TABLE public.uldaemo_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uldaemo_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uldaemo_state ENABLE ROW LEVEL SECURITY;

-- 기존 취약 정책 삭제
DROP POLICY IF EXISTS "uldaemo_users_api_policy" ON public.uldaemo_users;
DROP POLICY IF EXISTS "uldaemo_posts_api_policy" ON public.uldaemo_posts;
DROP POLICY IF EXISTS "uldaemo_state_api_policy" ON public.uldaemo_state;

-- anon / authenticated 직접 접근 전면 차단 (service_role만 접근 가능)
DROP POLICY IF EXISTS "deny_all_client_uldaemo_users" ON public.uldaemo_users;
CREATE POLICY "deny_all_client_uldaemo_users"
    ON public.uldaemo_users
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

DROP POLICY IF EXISTS "deny_all_client_uldaemo_posts" ON public.uldaemo_posts;
CREATE POLICY "deny_all_client_uldaemo_posts"
    ON public.uldaemo_posts
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

DROP POLICY IF EXISTS "deny_all_client_uldaemo_state" ON public.uldaemo_state;
CREATE POLICY "deny_all_client_uldaemo_state"
    ON public.uldaemo_state
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

-- 권한 최소화: anon / authenticated 역할에서 테이블 기본 권한도 회수
REVOKE ALL ON public.uldaemo_users FROM anon, authenticated;
REVOKE ALL ON public.uldaemo_posts FROM anon, authenticated;
REVOKE ALL ON public.uldaemo_state FROM anon, authenticated;
