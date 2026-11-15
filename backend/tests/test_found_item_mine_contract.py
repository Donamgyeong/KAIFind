"""ITEM-10 with actual PostgreSQL: own posts only, every state, newest first."""

import pytest

from found_item_fixtures import (  # noqa: F401
    ME, SUMMARY_KEYS, add_item, analysis_env, close, context, error, login, member, run,
    storage, three_items, titles,
)


def test_lists_only_own_items_newest_first_with_hidden_and_closed(context):
    client, env, body, headers, storage = context
    first, second, third = three_items(context)
    close(env, second, 'COLLECTED')
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=third['itemId'])

    other_headers = member(client, 'faculty-01')
    add_item(client, body, other_headers, 'someone else')
    member(client, 'student-01')

    response = client.get(ME)
    assert titles(response) == ['third', 'second', 'first']
    data = response.json()
    assert response.headers['cache-control'] == 'private, no-store'
    assert [item['hidden'] for item in data['items']] == [True, False, False]
    assert [item['status'] for item in data['items']] == ['POSTED', 'COLLECTED', 'POSTED']
    assert (data['page'], data['size'], data['totalElements'], data['totalPages']) == (0, 20, 3, 1)
    assert set(data['items'][0]) == SUMMARY_KEYS
    assert set(data['items'][0]['photos'][0]) == {'photoId', 'altText', 'accessRequiresLogin'}
    assert data['items'][0]['createdAt'].endswith('+09:00')
    assert 'someone else' not in response.text


def test_status_filter_accepts_repeated_values(context):
    client, env, body, headers, storage = context
    first, second, third = three_items(context)
    close(env, second, 'COLLECTED')
    close(env, first, 'EXPIRED')

    assert titles(client.get(ME, params={'statuses': ['COLLECTED', 'EXPIRED']})) == ['second', 'first']
    assert titles(client.get(ME, params={'statuses': 'POSTED'})) == ['third']
    assert titles(client.get(ME)) == ['third', 'second', 'first']


def test_pagination(context):
    client, env, body, headers, storage = context
    three_items(context)

    page = client.get(ME, params={'size': 2, 'page': 1}).json()
    assert [item['title'] for item in page['items']] == ['first']
    assert (page['page'], page['size'], page['totalElements'], page['totalPages']) == (1, 2, 3, 2)

    beyond = client.get(ME, params={'page': 5}).json()
    assert beyond['items'] == [] and beyond['totalElements'] == 3 and beyond['totalPages'] == 1


def test_deleted_items_are_excluded(context):
    client, env, body, headers, storage = context
    first, second, third = three_items(context)
    run(env, 'UPDATE found_items SET deleted_at=:now, purge_after=:later WHERE id=:id',
        now=env.clock(), later=env.clock(), id=second['itemId'])

    response = client.get(ME)
    assert titles(response) == ['third', 'first']
    assert response.json()['totalElements'] == 2


def test_member_without_items_gets_empty_page(context):
    client, env, body, headers, storage = context
    three_items(context)
    member(client, 'faculty-01')

    assert client.get(ME).json() == {
        'items': [], 'page': 0, 'size': 20, 'totalElements': 0, 'totalPages': 0,
    }


def test_admin_sees_only_own_items(context):
    client, env, body, headers, storage = context
    three_items(context)
    admin_headers = member(client, 'admin-01')
    add_item(client, body, admin_headers, 'admin item')

    assert titles(client.get(ME)) == ['admin item']


@pytest.mark.parametrize('params', [
    {'statuses': 'DELETED'}, {'page': -1}, {'size': 0}, {'size': 101}, {'page': 'x'},
    {'unknown': '1'}, {'q': 'wallet'},
])
def test_invalid_query_parameters(context, params):
    client, env, body, headers, storage = context
    error(client.get(ME, params=params), 400, 'VALIDATION_ERROR')


def test_authentication_and_openapi(context):
    client, env, body, headers, storage = context
    client.cookies.clear()
    error(client.get(ME), 401, 'AUTH_REQUIRED')

    operation = client.get('/openapi.json').json()['paths'][ME]['get']
    assert '501' not in operation['responses'] and operation['responses']['200']
