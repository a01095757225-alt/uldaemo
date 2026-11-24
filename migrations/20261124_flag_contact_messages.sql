-- ============================================================================
-- 울대모 (Uldaemo) 기존 채팅 메시지 연락처·SNS 요구 패턴 점검 및 운영진 검토 큐 등록 SQL
-- 작성일: 2026-11-24 | 브랜치: security/qa-round2-hardening
-- 원칙:
--   1) 점검 결과에는 메시지 본문/학번/이메일을 절대 출력하지 않고 건수와 ID만 출력합니다.
--   2) 기존 메시지는 삭제하지 않고 flagged=true 표시 + admin_review_queue 등록만 수행합니다.
--   3) 운영 DB에 자동 적용하지 않으며, 관리자 확인 후 Supabase SQL Editor에서 실행하세요.
-- ============================================================================

-- [1단계: 읽기 전용 점검 — 건수 및 대상 ID만 출력 (본문 미출력)]
WITH flagged_msgs AS (
    SELECT
        (m->>'id') AS message_id,
        (m->>'post_id') AS post_id,
        (m->>'created_at') AS created_at
    FROM public.uldaemo_state s,
         LATERAL jsonb_array_elements(COALESCE(s.data->'messages', '[]'::jsonb)) AS m
    WHERE s.id = 'main'
      AND COALESCE(m->>'sender_id', '') <> 'AI_BOT'
      AND (
          COALESCE(m->>'text', '') ~* '(01[016789]|공일공)[\s.\-]*[0-9]{3,4}[\s.\-]*[0-9]{4}'
          OR COALESCE(m->>'text', '') ~* '[a-z0-9_.+-]+@[a-z0-9-]+\.[a-z0-9-.]+'
          OR COALESCE(m->>'text', '') ~* '(^|\s)@[a-z0-9_.]{3,30}'
          OR COALESCE(m->>'text', '') ~* '(카톡|카카오|톡디|전번|전화번호|폰번|연락처|오픈채팅|옵챗|인스타|디엠|디스코드|텔레그램|kakao|insta|discord|telegram)'
          OR COALESCE(m->>'text', '') ~* '(번호|폰|아이디|계정|연락)\s*(좀|알려|교환|줘|주실|주세요|뭐|어떻게|보내|남겨)'
      )
)
SELECT
    COUNT(*) AS total_flagged_count,
    COALESCE(jsonb_agg(jsonb_build_object('message_id', message_id, 'post_id', post_id, 'created_at', created_at)), '[]'::jsonb) AS flagged_ids
FROM flagged_msgs;

-- [2단계: 비파괴 플래그 표시 및 운영진 검토 큐(admin_review_queue) 등록 — 관리자 확인 후 실행]
/*
BEGIN;

WITH target_ids AS (
    SELECT
        (m->>'id') AS msg_id_txt,
        (m->>'post_id') AS post_id_txt
    FROM public.uldaemo_state s,
         LATERAL jsonb_array_elements(COALESCE(s.data->'messages', '[]'::jsonb)) AS m
    WHERE s.id = 'main'
      AND COALESCE(m->>'sender_id', '') <> 'AI_BOT'
      AND (
          COALESCE(m->>'text', '') ~* '(01[016789]|공일공)[\s.\-]*[0-9]{3,4}[\s.\-]*[0-9]{4}'
          OR COALESCE(m->>'text', '') ~* '[a-z0-9_.+-]+@[a-z0-9-]+\.[a-z0-9-.]+'
          OR COALESCE(m->>'text', '') ~* '(^|\s)@[a-z0-9_.]{3,30}'
          OR COALESCE(m->>'text', '') ~* '(카톡|카카오|톡디|전번|전화번호|폰번|연락처|오픈채팅|옵챗|인스타|디엠|디스코드|텔레그램|kakao|insta|discord|telegram)'
          OR COALESCE(m->>'text', '') ~* '(번호|폰|아이디|계정|연락)\s*(좀|알려|교환|줘|주실|주세요|뭐|어떻게|보내|남겨)'
      )
),
updated_msgs AS (
    SELECT COALESCE(
        jsonb_agg(
            CASE
                WHEN (m->>'id') IN (SELECT msg_id_txt FROM target_ids)
                THEN m || jsonb_build_object('flagged', true, 'flag_reason', 'contact_pattern')
                ELSE m
            END
        ),
        '[]'::jsonb
    ) AS new_messages
    FROM public.uldaemo_state s,
         LATERAL jsonb_array_elements(COALESCE(s.data->'messages', '[]'::jsonb)) AS m
    WHERE s.id = 'main'
),
new_queue_items AS (
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'message_id', msg_id_txt,
                'post_id', post_id_txt,
                'flag_reason', 'contact_pattern',
                'flagged_at', (EXTRACT(EPOCH FROM now()) * 1000)::bigint,
                'status', 'pending'
            )
        ),
        '[]'::jsonb
    ) AS items
    FROM target_ids
)
UPDATE public.uldaemo_state
   SET data = jsonb_set(
         jsonb_set(
           data,
           '{messages}',
           (SELECT new_messages FROM updated_msgs),
           true
         ),
         '{admin_review_queue}',
         COALESCE(data->'admin_review_queue', '[]'::jsonb) || (SELECT items FROM new_queue_items),
         true
       ),
       updated_at = (EXTRACT(EPOCH FROM now()) * 1000)::bigint
 WHERE id = 'main';

COMMIT;
*/
