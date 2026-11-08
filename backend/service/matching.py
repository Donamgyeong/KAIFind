"""Read-only matching views and deterministic candidate evidence."""
from zoneinfo import ZoneInfo

from sqlalchemy import text

from library.text_analysis_types import AnalysisError
from schema.matching import MatchCandidatePage, MatchingProgress
from service.auth import AuthError


KST = ZoneInfo('Asia/Seoul')


def candidate_evidence(item, report, buildings, item_feature, report_feature):
    """Return only evidence supported by the supplied current-profile features."""
    if (item.deleted_at is not None or item.category_id != report.category_id
            or item.found_at.astimezone(KST).date() < report.lost_date_from):
        return False, ()

    ready = (
        item_feature is not None and report_feature is not None
        and item_feature.status == report_feature.status == 'READY'
        and item_feature.profile_id == report_feature.profile_id
        and item_feature.text_version == item.text_version
        and report_feature.text_version == report.text_version
    )
    keywords = tuple(sorted(set(item_feature.keywords) & set(report_feature.keywords))) if ready else ()
    return item.found_building_id in buildings, keywords


# One statement snapshot for authorization, status, visibility, count and page.
# No owner-private table, translation or analysis payload is selected into JSON.
VIEW = """
WITH r AS (
    SELECT *, (status <> 'OPEN' OR expires_at <= :now) AS historical
    FROM lost_reports WHERE id = :report_id
      AND (:internal OR owner_id = :user_id OR :admin)
), policy AS (
    SELECT p.id, p.analysis_profile_id FROM matching_runtime rt
    JOIN matching_policies p ON p.id = rt.active_policy_id WHERE rt.id = 1
), scope AS (
    SELECT i.* FROM found_items i CROSS JOIN r
    WHERE i.deleted_at IS NULL AND i.category_id = r.category_id
      AND timezone('Asia/Seoul', i.found_at)::date >= r.lost_date_from
), report_analysis AS (
    SELECT f.status FROM lost_report_text_features f CROSS JOIN r
    WHERE f.report_id = r.id AND f.text_version = r.text_version
      AND (r.historical OR f.profile_id = (SELECT analysis_profile_id FROM policy))
    ORDER BY f.created_at DESC, f.id DESC LIMIT 1
), states AS (
    SELECT coalesce((SELECT status FROM report_analysis), 'PENDING') AS state
    UNION ALL
    SELECT coalesce(f.status, 'PENDING') FROM scope i
    LEFT JOIN found_item_text_features f ON f.item_id = i.id
      AND f.profile_id = (SELECT analysis_profile_id FROM policy) AND f.text_version = i.text_version
    UNION ALL
    SELECT CASE
      WHEN j.id IS NULL THEN 'PENDING'
      WHEN j.completed_generation = j.requested_generation THEN 'READY'
      WHEN j.failed_at IS NOT NULL THEN 'FAILED'
      WHEN j.lease_until > :now THEN 'PROCESSING'
      ELSE 'PENDING' END
    FROM (SELECT id AS owner_id, true AS report FROM r
          UNION ALL SELECT id, false FROM scope) owners
    LEFT JOIN match_evaluation_jobs j ON j.policy_id = (SELECT id FROM policy)
      AND ((owners.report AND j.report_id = owners.owner_id)
        OR (NOT owners.report AND j.item_id = owners.owner_id))
), progress AS (
    SELECT CASE WHEN r.historical THEN 'READY'
      WHEN EXISTS (SELECT 1 FROM states WHERE state = 'FAILED') THEN 'FAILED'
      WHEN EXISTS (SELECT 1 FROM states WHERE state = 'PROCESSING') THEN 'PROCESSING'
      WHEN EXISTS (SELECT 1 FROM states WHERE state <> 'READY') THEN 'PENDING'
      ELSE 'READY' END AS matching,
      CASE WHEN (SELECT status FROM report_analysis) IN ('READY','FAILED','PROCESSING')
        THEN (SELECT status FROM report_analysis) ELSE 'PENDING' END AS analysis
    FROM r
), visible AS (
    SELECT c.id, c.report_id, c.item_id, c.matched_at, c.building_matched, c.keyword_matched,
      i.category_id, i.found_building_id, i.title, i.found_at, i.status, cat.sensitive
    FROM match_candidates c JOIN r ON r.id = c.report_id
    JOIN found_items i ON i.id = c.item_id JOIN categories cat ON cat.id = i.category_id
    LEFT JOIN found_item_text_features fi ON fi.id = c.item_feature_id
    LEFT JOIN lost_report_text_features fr ON fr.id = c.report_feature_id
    WHERE c.active AND i.deleted_at IS NULL AND (:admin OR NOT i.hidden)
      AND (r.historical OR (
        c.policy_id = (SELECT id FROM policy)
        AND c.analysis_profile_id = (SELECT analysis_profile_id FROM policy)
        AND c.evaluated_item_version = i.version AND c.evaluated_report_version = r.version
        AND i.category_id = r.category_id
        AND timezone('Asia/Seoul', i.found_at)::date >= r.lost_date_from
        AND (NOT c.keyword_matched OR (
          fi.status = 'READY' AND fr.status = 'READY'
          AND fi.text_version = i.text_version AND fr.text_version = r.text_version
          AND fi.profile_id = c.analysis_profile_id AND fr.profile_id = c.analysis_profile_id
        ))
      ))
), page_rows AS (
    SELECT * FROM visible ORDER BY matched_at DESC, id DESC LIMIT :size OFFSET :offset
)
SELECT progress.*, (SELECT id FROM policy) AS policy_id,
  (SELECT historical FROM r) AS historical,
  (SELECT count(*) FROM visible) AS total,
  coalesce((SELECT jsonb_agg(jsonb_build_object(
    'candidateId', id, 'reportId', report_id, 'itemId', item_id, 'matchedAt', matched_at,
    'matchedBy', CASE WHEN building_matched AND keyword_matched THEN '["BUILDING","KEYWORD"]'::jsonb
      WHEN building_matched THEN '["BUILDING"]'::jsonb ELSE '["KEYWORD"]'::jsonb END,
    'item', jsonb_build_object('itemId', item_id, 'categoryId', category_id,
      'foundBuildingId', found_building_id, 'title', title, 'foundAt', found_at,
      'status', status, 'sensitive', sensitive)
  ) ORDER BY matched_at DESC, id DESC) FROM page_rows), '[]'::jsonb) AS items
FROM progress
"""


async def read_matches(db, *, report_id, now, page=0, size=20, user_id=None, admin=False, internal=False):
    row = (await db.execute(text(VIEW), {
        'report_id': report_id, 'now': now, 'user_id': user_id,
        'admin': admin, 'internal': internal, 'size': size, 'offset': page * size,
    })).mappings().one_or_none()
    if row is None:
        raise AuthError(404, 'LOST_REPORT_NOT_FOUND')
    if row['policy_id'] is None and not row['historical']:
        raise AnalysisError('MATCHING_POLICY_NOT_CONFIGURED')

    return MatchCandidatePage(
        items=row['items'], page=page, size=size, totalElements=row['total'],
        totalPages=(row['total'] + size - 1) // size,
        analysisStatus=row['analysis'], matchingStatus=row['matching'],
        isComplete=row['matching'] == 'READY',
    )


async def matching_progress(db, *, report, now):
    """Stage 4 integration: no mutation, inference or transaction ownership."""
    result = await read_matches(db, report_id=report.id, now=now, internal=True, size=1)
    return MatchingProgress(analysisStatus=result.analysis_status, matchingStatus=result.matching_status)
