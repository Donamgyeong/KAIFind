"""ITEM-04 edit, ITEM-05 delete and ITEM-09 repost against PostgreSQL and MinIO."""

from datetime import timedelta
from uuid import uuid4

import pytest

from found_item_fixtures import (  # noqa: F401
    BASE, analysis_env, add_item, close, context, error, guest, login, member, other_building,
    run, scalar, sensitive_category, storage, upload,
)


def url(item):
    return f"{BASE}/{item['itemId']}"


def patch(client, item, headers, **payload):
    return client.patch(url(item), json=payload, headers=headers)


def gallery(client, body, headers, title='gallery'):
    """An item with two photos; returns (item, [photo ids])."""
    ids = [upload(client, headers).json()['photoId'] for _ in range(2)]
    payload = {**body, 'title': title, 'photos': [
        {'photoId': ids[0], 'altText': 'first'}, {'photoId': ids[1], 'altText': 'second'},
    ]}
    response = client.post(BASE, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json(), ids


# ------------------------------------------------------------------ ITEM-04

def test_patch_text_change_requests_new_analysis(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'old title')
    features = 'SELECT count(*) FROM found_item_text_features WHERE item_id=:id'
    generation = 'SELECT requested_generation FROM match_evaluation_jobs WHERE item_id=:id'
    before = (scalar(env, features, id=item['itemId']), scalar(env, generation, id=item['itemId']))

    response = patch(client, item, headers, title=' new title ')
    assert response.status_code == 200, response.text
    result = response.json()
    assert response.headers['cache-control'] == 'private, no-store'
    assert result['title'] == 'new title' and result['description'] == item['description']
    assert result['updatedAt'] == '2026-11-03T10:00:00+09:00'
    assert result['status'] == 'POSTED' and result['hidden'] is False
    assert scalar(env, features, id=item['itemId']) == before[0] + 1
    assert scalar(env, generation, id=item['itemId']) > before[1]


def test_patch_without_text_change_only_reevaluates(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'same text')
    features = 'SELECT count(*) FROM found_item_text_features WHERE item_id=:id'
    generation = 'SELECT requested_generation FROM match_evaluation_jobs WHERE item_id=:id'
    before = (scalar(env, features, id=item['itemId']), scalar(env, generation, id=item['itemId']))

    response = patch(client, item, headers, foundLocationDescription='  Second floor  ', title='same text')
    assert response.status_code == 200, response.text
    assert response.json()['foundLocationDescription'] == 'Second floor'
    assert scalar(env, features, id=item['itemId']) == before[0]
    assert scalar(env, generation, id=item['itemId']) > before[1]


def test_patch_keeps_status_hidden_and_works_on_closed_items(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'closed one')
    close(env, item, 'COLLECTED')
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=item['itemId'])

    response = patch(client, item, headers, description='edited after collection')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'COLLECTED' and response.json()['hidden'] is True
    assert response.json()['closedAt'] is not None


@pytest.mark.parametrize('payload', [
    {}, {'title': None}, {'title': ' '}, {'description': ''}, {'photos': []}, {'photos': None},
    {'status': 'EXPIRED'}, {'hidden': True}, {'finderId': 'x'}, {'sensitive': True},
    {'dropOff': {'mode': 'KEPT_BY_FINDER'}}, {'foundAt': '2099-01-01T00:00:00+09:00'},
    {'foundAt': '2026-11-01T00:00:00'}, {'foundAt': 5}, {'categoryId': 'not-a-uuid'},
])
def test_patch_rejects_invalid_bodies(context, payload):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'untouched')

    error(client.patch(url(item), json=payload, headers=headers), 400, 'VALIDATION_ERROR')
    assert client.get(url(item)).json()['title'] == 'untouched'


def test_patch_rejects_duplicate_photo_ids(context):
    client, env, body, headers, storage = context
    item, (a, b) = gallery(client, body, headers)
    photo = {'photoId': a, 'altText': 'dup'}

    error(patch(client, item, headers, photos=[photo, photo]), 400, 'VALIDATION_ERROR')


def test_patch_authorization(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'protected')

    other = member(client, 'faculty-01')
    error(patch(client, item, other, title='x'), 403, 'FORBIDDEN')
    admin = member(client, 'admin-01')
    error(patch(client, item, admin, title='x'), 403, 'FORBIDDEN')  # admins are not editors

    guest(client)
    error(client.patch(url(item), json={'title': 'x'}), 401, 'AUTH_REQUIRED')
    headers = member(client, 'student-01')  # a fresh session has a fresh CSRF token
    error(client.patch(url(item), json={'title': 'x'}), 403, 'CSRF_INVALID')
    error(client.patch(url(item), content='{}', headers={**headers, 'Content-Type': 'text/plain'}),
          415, 'UNSUPPORTED_MEDIA_TYPE')
    assert client.get(url(item)).json()['title'] == 'protected'


def test_patch_missing_deleted_and_hidden_targets(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'target')
    error(client.patch(f'{BASE}/{uuid4()}', json={'title': 'x'}, headers=headers), 404, 'NOT_FOUND')

    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=item['itemId'])
    other = member(client, 'faculty-01')
    error(patch(client, item, other, title='x'), 404, 'NOT_FOUND')  # existence stays hidden

    member(client, 'student-01')
    run(env, 'UPDATE found_items SET deleted_at=:now, purge_after=:later WHERE id=:id',
        now=env.clock(), later=env.clock(), id=item['itemId'])
    headers = member(client, 'student-01')
    error(patch(client, item, headers, title='x'), 404, 'NOT_FOUND')


def test_patch_reference_rules(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'refs')
    other = other_building(env)
    run(env, 'UPDATE buildings SET active=false WHERE id=:id', id=body['foundBuildingId'])

    # An already used inactive building may stay; choosing an inactive one is refused.
    assert patch(client, item, headers, title='still ok').status_code == 200
    run(env, 'UPDATE buildings SET active=false WHERE id=:id', id=other)
    error(patch(client, item, headers, foundBuildingId=str(other)), 400, 'INVALID_REFERENCE')
    error(patch(client, item, headers, foundBuildingId=str(uuid4())), 400, 'INVALID_REFERENCE')
    error(patch(client, item, headers, categoryId=str(uuid4())), 400, 'INVALID_REFERENCE')

    run(env, 'UPDATE buildings SET active=true WHERE id=:id', id=other)
    changed = patch(client, item, headers, foundBuildingId=str(other)).json()
    assert changed['foundBuilding']['buildingId'] == str(other)


def test_patch_photo_reorder_replace_and_detach(context):
    client, env, body, headers, storage = context
    item, (a, b) = gallery(client, body, headers)

    swapped = patch(client, item, headers, photos=[
        {'photoId': b, 'altText': 'B first'}, {'photoId': a, 'altText': 'A second'},
    ])
    assert swapped.status_code == 200, swapped.text
    assert [(p['photoId'], p['altText']) for p in swapped.json()['photos']] == [
        (b, 'B first'), (a, 'A second'),
    ]

    c = upload(client, headers).json()['photoId']
    replaced = patch(client, item, headers, photos=[
        {'photoId': c, 'altText': 'C'}, {'photoId': a, 'altText': 'A'},
    ])
    assert [p['photoId'] for p in replaced.json()['photos']] == [c, a]
    assert [p['photoId'] for p in client.get(url(item)).json()['photos']] == [c, a]

    # The dropped photo is detached, not erased, and cannot come back.
    assert scalar(env, 'SELECT detached_at IS NOT NULL FROM photo_attachments WHERE photo_id=:id', id=b)
    assert scalar(env, 'SELECT count(*) FROM photos WHERE id=:id', id=b) == 1
    error(patch(client, item, headers, photos=[{'photoId': b, 'altText': 'back'}]),
          409, 'PHOTO_ALREADY_ATTACHED')


def test_patch_photo_errors_roll_back_every_change(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'before')
    other_item = add_item(client, body, headers, 'taken')
    taken = other_item['photos'][0]['photoId']

    other = member(client, 'faculty-01')
    foreign = upload(client, other).json()['photoId']
    headers = member(client, 'student-01')

    error(patch(client, item, headers, title='after', photos=[{'photoId': foreign, 'altText': 'x'}]),
          403, 'PHOTO_FORBIDDEN')
    error(patch(client, item, headers, title='after', photos=[{'photoId': taken, 'altText': 'x'}]),
          409, 'PHOTO_ALREADY_ATTACHED')
    error(patch(client, item, headers, title='after', photos=[{'photoId': str(uuid4()), 'altText': 'x'}]),
          400, 'INVALID_REFERENCE')

    after = client.get(url(item)).json()
    assert after['title'] == 'before' and len(after['photos']) == 1


def test_patch_category_changes_protection_labels(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'moving')
    sensitive = sensitive_category(env)

    upgraded = patch(client, item, headers, categoryId=str(sensitive)).json()
    assert upgraded['sensitive'] is True and upgraded['photos'][0]['accessRequiresLogin'] is True

    # Moving back must never relax protection of photos that were once protected.
    downgraded = patch(client, item, headers, categoryId=str(env.ids['category'])).json()
    assert downgraded['sensitive'] is False and downgraded['photos'][0]['accessRequiresLogin'] is True
    guest(client)
    assert client.get(url(item)).json()['photos'] == []


def test_patch_with_category_and_photos_together_reports_fresh_labels(context):
    client, env, body, headers, storage = context
    item, (a, b) = gallery(client, body, headers)
    sensitive = sensitive_category(env)

    result = patch(client, item, headers, categoryId=str(sensitive), photos=[
        {'photoId': b, 'altText': 'B'}, {'photoId': a, 'altText': 'A'},
    ]).json()
    assert [p['accessRequiresLogin'] for p in result['photos']] == [True, True]


# ------------------------------------------------------------------ ITEM-05

def test_delete_is_logical_and_triggers_cleanup(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'to delete')
    other = add_item(client, body, headers, 'kept')

    response = client.delete(url(item), headers=headers)
    assert response.status_code == 204 and response.content == b''
    assert scalar(env, 'SELECT deleted_at IS NOT NULL FROM found_items WHERE id=:id', id=item['itemId'])
    assert scalar(env, 'SELECT purge_after FROM found_items WHERE id=:id', id=item['itemId']) == \
        env.clock().replace(year=env.clock().year + 1)
    assert scalar(env, "SELECT status FROM found_items WHERE id=:id", id=item['itemId']) == 'POSTED'
    # Analysis rows and evaluation jobs are removed by the DB cleanup trigger.
    assert scalar(env, 'SELECT count(*) FROM found_item_text_features WHERE item_id=:id', id=item['itemId']) == 0
    assert scalar(env, 'SELECT count(*) FROM match_evaluation_jobs WHERE item_id=:id', id=item['itemId']) == 0
    assert scalar(env, 'SELECT count(*) FROM found_item_text_features WHERE item_id=:id', id=other['itemId']) == 1

    error(client.get(url(item)), 404, 'NOT_FOUND')
    guest(client)
    error(client.get(url(item)), 404, 'NOT_FOUND')
    assert [i['title'] for i in client.get(BASE).json()['items']] == ['kept']
    member(client, 'student-01')
    assert [i['title'] for i in client.get('/api/v1/me/found-items').json()['items']] == ['kept']


def test_delete_keeps_the_retention_date_of_a_closed_item(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'closed')
    close(env, item, 'COLLECTED')
    original = env.clock() + timedelta(days=100)
    run(env, 'UPDATE found_items SET purge_after=:p WHERE id=:id', p=original, id=item['itemId'])

    assert client.delete(url(item), headers=headers).status_code == 204
    assert scalar(env, 'SELECT purge_after FROM found_items WHERE id=:id', id=item['itemId']) == original
    assert scalar(env, "SELECT status FROM found_items WHERE id=:id", id=item['itemId']) == 'COLLECTED'


def test_delete_rules(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'guarded')

    # A DELETE has no body contract, so a non-empty one is refused.
    error(client.request('DELETE', url(item), headers=headers, content='{}'), 400, 'VALIDATION_ERROR')
    other = member(client, 'faculty-01')
    error(client.delete(url(item), headers=other), 403, 'FORBIDDEN')
    admin = member(client, 'admin-01')
    error(client.delete(url(item), headers=admin), 403, 'FORBIDDEN')
    guest(client)
    error(client.delete(url(item)), 401, 'AUTH_REQUIRED')

    headers = member(client, 'student-01')
    error(client.delete(url(item)), 403, 'CSRF_INVALID')
    assert client.delete(url(item), headers=headers).status_code == 204
    error(client.delete(url(item), headers=headers), 404, 'NOT_FOUND')
    error(client.delete(f'{BASE}/{uuid4()}', headers=headers), 404, 'NOT_FOUND')


# ------------------------------------------------------------------ ITEM-09

def test_repost_restores_an_expired_item(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'expired one')
    close(env, item, 'EXPIRED')
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=item['itemId'])

    response = client.post(f"{url(item)}/repost", headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'POSTED' and result['closedAt'] is None
    assert result['hidden'] is True  # a repost never lifts a moderation hide
    assert result['postedAt'] == '2026-11-03T10:00:00+09:00'
    assert result['expiresAt'] == '2026-12-03T10:00:00+09:00'
    assert scalar(env, 'SELECT purge_after IS NULL FROM found_items WHERE id=:id', id=item['itemId'])
    assert scalar(env, """SELECT count(*) FROM audit_logs WHERE target_id=:id AND action='ITEM_STATUS_CHANGED'
        AND metadata->>'fromStatus'='EXPIRED' AND metadata->>'toStatus'='POSTED'""", id=item['itemId']) == 1


def test_repost_requires_an_expired_item(context):
    client, env, body, headers, storage = context
    posted = add_item(client, body, headers, 'posted')
    collected = add_item(client, body, headers, 'collected')
    close(env, collected, 'COLLECTED')

    for item in (posted, collected):
        error(client.post(f"{url(item)}/repost", headers=headers), 409, 'ITEM_NOT_EXPIRED')

    english = client.post(f"{url(posted)}/repost", headers={**headers, 'Accept-Language': 'en'})
    assert english.json()['message'] == 'Only expired items can be reposted.'
    assert english.headers['content-language'] == 'en'


def test_repost_authorization_and_targets(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'expired')
    close(env, item, 'EXPIRED')

    other = member(client, 'faculty-01')
    error(client.post(f"{url(item)}/repost", headers=other), 403, 'FORBIDDEN')
    admin = member(client, 'admin-01')
    error(client.post(f"{url(item)}/repost", headers=admin), 403, 'FORBIDDEN')
    guest(client)
    error(client.post(f"{url(item)}/repost"), 401, 'AUTH_REQUIRED')

    headers = member(client, 'student-01')
    error(client.post(f'{BASE}/{uuid4()}/repost', headers=headers), 404, 'NOT_FOUND')
    run(env, 'UPDATE found_items SET deleted_at=:now, purge_after=:later WHERE id=:id',
        now=env.clock(), later=env.clock(), id=item['itemId'])
    error(client.post(f"{url(item)}/repost", headers=headers), 404, 'NOT_FOUND')


def test_repost_followed_by_expiry_cycle_is_repeatable(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'again')
    for _ in range(2):
        close(env, item, 'EXPIRED')
        assert client.post(f"{url(item)}/repost", headers=headers).status_code == 200
    assert client.get(url(item)).json()['status'] == 'POSTED'


def test_openapi_has_no_501_for_item_operations(context):
    client, env, body, headers, storage = context
    paths = client.get('/openapi.json').json()['paths']
    for path, method in ((BASE + '/{itemId}', 'patch'), (BASE + '/{itemId}', 'delete'),
                         (BASE + '/{itemId}/repost', 'post')):
        assert '501' not in paths[path][method]['responses']
    assert paths[BASE + '/{itemId}']['delete']['responses']['204'] is not None
