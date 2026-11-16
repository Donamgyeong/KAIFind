"""ITEM-01 search and ITEM-02 detail: guests, members, hidden and protected-photo rules."""

from uuid import uuid4

import pytest

from service.auth import IDLE
from found_item_fixtures import (  # noqa: F401
    BASE, DETAIL_KEYS, SUMMARY_KEYS, add_item, analysis_env, close, context, error, guest,
    login, member, other_building, run, scalar, sensitive_category, space_out, storage,
    three_items, titles,
)


def test_guest_list_defaults_to_posted_and_hides_hidden_and_deleted(context):
    client, env, body, headers, storage = context
    first, second, third = three_items(context)
    fourth = add_item(client, body, headers, 'fourth')
    close(env, second, 'COLLECTED')
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=third['itemId'])
    run(env, 'UPDATE found_items SET deleted_at=:now, purge_after=:later WHERE id=:id',
        now=env.clock(), later=env.clock(), id=fourth['itemId'])

    guest(client)
    response = client.get(BASE)
    assert titles(response) == ['first']
    assert response.headers['cache-control'] == 'private, no-store'
    assert set(response.json()['items'][0]) == SUMMARY_KEYS
    assert response.json()['totalElements'] == 1

    assert titles(client.get(BASE, params={'statuses': 'COLLECTED'})) == ['second']
    everything = client.get(BASE, params={'statuses': ['POSTED', 'COLLECTED', 'EXPIRED']})
    assert titles(everything) == ['second', 'first']  # the hidden third is never public


def test_hidden_items_are_not_listed_even_for_their_finder(context):
    client, env, body, headers, storage = context
    first, second, third = three_items(context)
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=third['itemId'])

    assert titles(client.get(BASE)) == ['second', 'first']


def test_search_filters(context):
    client, env, body, headers, storage = context
    other = other_building(env)
    a = add_item(client, body, headers, 'Black Wallet', description='found near the library')
    b = add_item(client, body, headers, '100% real_item', description='plain',
                 foundBuildingId=str(other))
    c = add_item(client, body, headers, 'Umbrella', description='blue WALLET holder')
    space_out(env, [a, b, c])
    for item, found_at in ((a, '2026-11-01T23:30:00+09:00'), (b, '2026-11-02T00:30:00+09:00'),
                           (c, '2026-11-03T10:00:00+09:00')):
        run(env, 'UPDATE found_items SET found_at=:at WHERE id=:id', at=found_at, id=item['itemId'])
    guest(client)

    # Keyword: title or description, case-insensitive.
    assert titles(client.get(BASE, params={'q': 'wallet'})) == ['Umbrella', 'Black Wallet']
    assert titles(client.get(BASE, params={'q': ' LIBRARY '})) == ['Black Wallet']
    # LIKE wildcards are literal characters, not patterns.
    assert titles(client.get(BASE, params={'q': '%'})) == ['100% real_item']
    assert titles(client.get(BASE, params={'q': '_'})) == ['100% real_item']
    assert titles(client.get(BASE, params={'q': 'real%'})) == []

    assert titles(client.get(BASE, params={'foundBuildingId': str(other)})) == ['100% real_item']
    assert len(titles(client.get(BASE, params={'categoryId': str(env.ids['category'])}))) == 3
    assert titles(client.get(BASE, params={'categoryId': str(uuid4())})) == []

    # Dates are KST calendar days with an inclusive end day.
    assert titles(client.get(BASE, params={'foundDateFrom': '2026-11-02'})) == ['Umbrella', '100% real_item']
    assert titles(client.get(BASE, params={'foundDateTo': '2026-11-02'})) == ['100% real_item', 'Black Wallet']
    assert titles(client.get(BASE, params={
        'foundDateFrom': '2026-11-02', 'foundDateTo': '2026-11-02',
    })) == ['100% real_item']
    assert titles(client.get(BASE, params={'foundDateTo': '2026-11-01'})) == ['Black Wallet']


def test_search_pagination_counts_only_visible_rows(context):
    client, env, body, headers, storage = context
    three_items(context)
    guest(client)

    page = client.get(BASE, params={'size': 2, 'page': 1}).json()
    assert [item['title'] for item in page['items']] == ['first']
    assert (page['totalElements'], page['totalPages']) == (3, 2)


def test_search_accepts_maximum_end_date(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'within date range')
    guest(client)

    response = client.get(BASE, params={'foundDateTo': '9999-12-31'})

    assert response.status_code == 200, response.text
    data = response.json()
    assert [row['itemId'] for row in data['items']] == [item['itemId']]
    assert (data['totalElements'], data['totalPages']) == (1, 1)


@pytest.mark.parametrize('params', [
    {'q': ' '}, {'q': 'x' * 101}, {'foundDateFrom': '2026/11/01'}, {'foundDateFrom': '20261101'},
    {'foundDateFrom': '2026-11-05', 'foundDateTo': '2026-11-01'}, {'categoryId': 'nope'},
    {'statuses': 'DELETED'}, {'size': 101}, {'page': -1}, {'unknown': '1'},
])
def test_invalid_search_parameters(context, params):
    client, env, body, headers, storage = context
    guest(client)
    error(client.get(BASE, params=params), 400, 'VALIDATION_ERROR')


def test_guest_never_sees_protected_photo_metadata(context):
    client, env, body, headers, storage = context
    plain = add_item(client, body, headers, 'plain')
    protected = add_item(client, body, headers, 'protected', categoryId=str(sensitive_category(env)))

    guest(client)
    listing = {item['title']: item for item in client.get(BASE).json()['items']}
    assert listing['plain']['photos'][0]['accessRequiresLogin'] is False
    assert listing['protected']['photos'] == [] and listing['protected']['sensitive'] is True

    detail = client.get(f"{BASE}/{protected['itemId']}")
    assert detail.status_code == 200 and detail.json()['photos'] == []
    assert 'protected photo' not in detail.text

    member(client, 'faculty-01')
    seen = client.get(f"{BASE}/{protected['itemId']}").json()['photos']
    assert seen[0]['altText'] == 'protected photo' and seen[0]['accessRequiresLogin'] is True


def test_protection_label_survives_a_later_non_sensitive_category(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'once sensitive', categoryId=str(sensitive_category(env)))
    run(env, 'UPDATE found_items SET category_id=:category WHERE id=:id',
        category=env.ids['category'], id=item['itemId'])

    guest(client)
    detail = client.get(f"{BASE}/{item['itemId']}").json()
    assert detail['sensitive'] is False and detail['photos'] == []


def test_detail_for_guest_and_member(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'visible')

    guest(client)
    response = client.get(f"{BASE}/{item['itemId']}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['content-language'] == 'ko'
    assert DETAIL_KEYS <= set(data)
    assert set(data['finder']) == {'userId'}
    assert 'email' not in response.text and 'dropOff' not in data
    assert data['title'] == 'visible' and data['status'] == 'POSTED' and data['closedAt'] is None
    assert data['analysisStatus'] in {'PENDING', 'PROCESSING', 'READY', 'FAILED'}
    assert data['createdAt'].endswith('+09:00') and data['expiresAt'].endswith('+09:00')

    member(client, 'faculty-01')
    assert client.get(f"{BASE}/{item['itemId']}").json() == data


def test_hidden_item_detail_is_limited_to_finder_and_admin(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'secret')
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=item['itemId'])
    url = f"{BASE}/{item['itemId']}"

    guest(client)
    error(client.get(url), 404, 'NOT_FOUND')
    member(client, 'faculty-01')
    error(client.get(url), 404, 'NOT_FOUND')
    member(client, 'admin-01')
    assert client.get(url).status_code == 200
    member(client, 'student-01')
    assert client.get(url).json()['hidden'] is True


def test_deleted_unknown_and_malformed_ids(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'gone')
    run(env, 'UPDATE found_items SET deleted_at=:now, purge_after=:later WHERE id=:id',
        now=env.clock(), later=env.clock(), id=item['itemId'])

    error(client.get(f"{BASE}/{item['itemId']}"), 404, 'NOT_FOUND')  # even for its finder
    error(client.get(f'{BASE}/{uuid4()}'), 404, 'NOT_FOUND')
    error(client.get(f'{BASE}/not-a-uuid'), 400, 'VALIDATION_ERROR')


def test_invalid_and_expired_sessions_are_plain_guests(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'mine')
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=item['itemId'])
    url = f"{BASE}/{item['itemId']}"

    # A hidden post is still visible to its finder while the session is alive ...
    assert client.get(url).status_code == 200
    # ... but an expired session is only a guest, and public reads never answer 401.
    env.clock.advance(hours=13)
    error(client.get(url), 404, 'NOT_FOUND')
    assert client.get(BASE).status_code == 200

    guest(client)
    assert client.get(BASE, headers={'Cookie': 'KAIFIND_SESSION=garbage'}).status_code == 200


def test_anonymous_csrf_session_is_a_plain_guest(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'secret')
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=item['itemId'])

    guest(client)
    assert client.get('/api/v1/auth/csrf').status_code == 200  # a session cookie without a login
    assert client.get(BASE).status_code == 200
    error(client.get(f"{BASE}/{item['itemId']}"), 404, 'NOT_FOUND')


def test_public_reads_count_as_activity_for_a_member_session(context):
    client, env, body, headers, storage = context
    # Two steps are each shorter than the idle timeout but together longer than it.
    step = IDLE * 2 // 3
    env.clock.advance(seconds=step.total_seconds())
    assert client.get(BASE).status_code == 200
    env.clock.advance(seconds=step.total_seconds())
    assert client.get('/api/v1/auth/me').status_code == 200


def test_openapi_documents_both_public_operations(context):
    client, env, body, headers, storage = context
    paths = client.get('/openapi.json').json()['paths']
    for path in (BASE, BASE + '/{itemId}'):
        operation = paths[path]['get']
        assert '501' not in operation['responses'] and operation['responses']['200']
        cookie = next(p for p in operation['parameters'] if p['name'] == 'KAIFIND_SESSION')
        assert cookie['required'] is False
