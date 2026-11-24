-- ============================================================================
-- 울대모 (Uldaemo) 운영 DB 잔존 QA/테스트 데이터 정리 SQL (확인 후 수동 실행)
-- 작성일: 2026-11-24 | 브랜치: fix/qa-top10-issues
-- 주의: 먼저 [1단계 조회] 쿼리로 삭제 대상을 확인한 뒤, 이상 없을 때만 [2단계 삭제]를 실행하세요.
-- ============================================================================

-- [1단계: 삭제 대상 사전 조회 — 읽기 전용]
SELECT id, author_id, title, meet_date, status
  FROM public.uldaemo_posts
 WHERE title ILIKE '%[QA테스트]%'
    OR title ILIKE '%[테스트]%'
    OR title ILIKE '%점검용%'
    OR id IN (101, 102, 103);

SELECT student_id, nickname, email, joined_at
  FROM public.uldaemo_users
 WHERE student_id IN ('20241001', '20241002', '20241003', 'demo_me', 'demo_m1', 'demo_m2')
    OR email ILIKE '%@test.local'
    OR email ILIKE '%@example.com'
    OR nickname ILIKE '%QA테스트%';

-- [2단계: 실제 삭제 — 관리자 최종 확인 후 BEGIN ~ COMMIT 블록 실행]
/*
BEGIN;

-- 2-1. uldaemo_posts 테이블에서 QA/테스트 번개 삭제
DELETE FROM public.uldaemo_posts
 WHERE title ILIKE '%[QA테스트]%'
    OR title ILIKE '%[테스트]%'
    OR title ILIKE '%점검용%'
    OR id IN (101, 102, 103);

-- 2-2. uldaemo_users 테이블에서 테스트 계정 삭제
DELETE FROM public.uldaemo_users
 WHERE student_id IN ('20241001', '20241002', '20241003', 'demo_me', 'demo_m1', 'demo_m2')
    OR email ILIKE '%@test.local'
    OR email ILIKE '%@example.com'
    OR nickname ILIKE '%QA테스트%';

-- 2-3. uldaemo_state(id='main') JSONB 내부 posts 배열에서 테스트 번개 제거
UPDATE public.uldaemo_state
   SET data = jsonb_set(
         data,
         '{posts}',
         COALESCE(
           (
             SELECT jsonb_agg(p)
               FROM jsonb_array_elements(COALESCE(data->'posts', '[]'::jsonb)) AS p
              WHERE COALESCE(p->>'title', '') NOT ILIKE '%[QA테스트]%'
                AND COALESCE(p->>'title', '') NOT ILIKE '%[테스트]%'
                AND COALESCE(p->>'title', '') NOT ILIKE '%점검용%'
                AND COALESCE((p->>'id')::bigint, 0) NOT IN (101, 102, 103)
           ),
           '[]'::jsonb
         ),
         true
       ),
       updated_at = (EXTRACT(EPOCH FROM now()) * 1000)::bigint
 WHERE id = 'main';

COMMIT;
*/
