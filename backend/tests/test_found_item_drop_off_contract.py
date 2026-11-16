"""ITEM-06/07/08: storage spot reads, appended revisions and history, with audit rules."""

import asyncio
import threading
from uuid import uuid4

import pytest
from sqlalchemy import text

from service.found_items import FoundItemService
from found_item_fixtures import (  # noqa: F401
    BASE, analysis_env, add_item, context, error, guest, login, member, other_building, run,
    scalar, sensitive_category, storage, upload,
)


def spot(item):
    return f"{BASE}/{item['itemId']}/drop-off"


def put(client, item, headers, **payload):
    return client.put(spot(item), json=payload, headers=headers)


def desk(body, text='Front desk'):
    return {'mode': 'DROP_OFF', 'buildingId': body['foundBuildingId'], 'spotDescription': text}


def located(client, body, headers, title='located', **changes):
    return add_item(client, body, headers, title, dropOff=desk(body), **changes)


def audits(env, item, action):
    return scalar(env, 'SELECT count(*) FROM audit_logs WHERE target_id=:id AND action=:action',
                  id=item['itemId'], action=action)


def revisions(env, item):
    return scalar(env, 'SELECT count(*) FROM drop_off_versions WHERE item_id=:id', id=item['itemId'])


# ------------------------------------------------------------------ ITEM-06

def test_kept_by_finder_has_no_location(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'kept')

    member(client, 'faculty-01')
    response = client.get(spot(item))
    assert response.status_code == 200, response.text
    assert response.json() == {
        'mode': 'KEPT_BY_FINDER', 'building': None, 'spotDescription': None, 'photo': None,
        'updatedAt': '2026-11-03T10:00:00+09:00',
    }
    assert response.headers['cache-control'] == 'private, no-store'
    assert audits(env, item, 'SENSITIVE_DROP_OFF_VIEWED') == 0


def test_drop_off_spot_is_for_members_only(context):
    client, env, body, headers, storage = context
    item = located(client, body, headers)

    member(client, 'faculty-01')
    data = client.get(spot(item)).json()
    assert data['mode'] == 'DROP_OFF' and data['spotDescription'] == 'Front desk'
    assert data['building']['buildingId'] == body['foundBuildingId'] and data['photo'] is None

    guest(client)
    error(client.get(spot(item)), 401, 'AUTH_REQUIRED')
    # The spot never leaks through the public detail or list.
    assert 'Front desk' not in client.get(f"{BASE}/{item['itemId']}").text
    assert 'Front desk' not in client.get(BASE).text


def test_sensitive_reads_are_audited_every_time(context):
    client, env, body, headers, storage = context
    item = located(client, body, headers, 'vault', categoryId=str(sensitive_category(env)))

    member(client, 'faculty-01')
    assert client.get(spot(item)).status_code == 200
    assert client.get(spot(item)).status_code == 200
    assert audits(env, item, 'SENSITIVE_DROP_OFF_VIEWED') == 2
    assert scalar(env, """SELECT count(*) FROM audit_logs WHERE target_id=:id AND actor_id IS NOT NULL
        AND action='SENSITIVE_DROP_OFF_VIEWED' AND actor_type='MEMBER'""", id=item['itemId']) == 2


def test_nothing_is_delivered_when_the_audit_cannot_be_stored(context, monkeypatch):
    client, env, body, headers, storage = context
    item = located(client, body, headers, 'vault', categoryId=str(sensitive_category(env)))

    def fail(*args, **kwargs):
        raise RuntimeError('simulated audit failure')

    monkeypatch.setattr('service.found_items.append_audit', fail)
    member(client, 'faculty-01')
    response = client.get(spot(item))
    error(response, 500, 'INTERNAL_SERVER_ERROR')
    assert 'Front desk' not in response.text


def test_drop_off_reads_follow_item_visibility(context):
    client, env, body, headers, storage = context
    item = located(client, body, headers)
    run(env, 'UPDATE found_items SET hidden=true WHERE id=:id', id=item['itemId'])

    other = member(client, 'faculty-01')
    error(client.get(spot(item)), 404, 'NOT_FOUND')
    error(client.get(spot(item) + '/history'), 404, 'NOT_FOUND')
    member(client, 'admin-01')
    assert client.get(spot(item)).status_code == 200
    member(client, 'student-01')
    assert client.get(spot(item)).status_code == 200

    run(env, 'UPDATE found_items SET deleted_at=:now, purge_after=:later WHERE id=:id',
        now=env.clock(), later=env.clock(), id=item['itemId'])
    error(client.get(spot(item)), 404, 'NOT_FOUND')
    error(client.get(f'{BASE}/{uuid4()}/drop-off'), 404, 'NOT_FOUND')


# ------------------------------------------------------------------ ITEM-07

def test_change_appends_a_revision_and_keeps_everything_else(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'moving')
    before = client.get(f"{BASE}/{item['itemId']}").json()

    response = put(client, item, headers, **desk(body))
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.json()['mode'] == 'DROP_OFF' and response.json()['spotDescription'] == 'Front desk'

    assert client.get(spot(item)).json() == response.json()
    after = client.get(f"{BASE}/{item['itemId']}").json()
    assert after['foundLocationDescription'] == before['foundLocationDescription']
    assert after['status'] == before['status'] and after['updatedAt'] == before['updatedAt']
    assert revisions(env, item) == 2
    assert audits(env, item, 'DROP_OFF_CHANGED') == 2  # registration + this change
    assert audits(env, item, 'SENSITIVE_DROP_OFF_VIEWED') == 0


def test_history_shows_before_and_after_across_pages(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'travelling')
    assert put(client, item, headers, **desk(body, 'Desk A')).status_code == 200
    assert put(client, item, headers, mode='KEPT_BY_FINDER').status_code == 200
    assert revisions(env, item) == 3

    history = client.get(spot(item) + '/history').json()
    assert (history['page'], history['size'], history['totalElements'], history['totalPages']) == (0, 20, 3, 1)
    newest, middle, oldest = history['items']
    assert (newest['after']['mode'], newest['before']['mode']) == ('KEPT_BY_FINDER', 'DROP_OFF')
    assert middle['after']['spotDescription'] == 'Desk A' and middle['before']['mode'] == 'KEPT_BY_FINDER'
    assert oldest['before'] is None and oldest['after']['mode'] == 'KEPT_BY_FINDER'
    assert newest['changedByUserId'] == oldest['changedByUserId']
    assert newest['changedAt'].endswith('+09:00') and newest['historyId'] != middle['historyId']

    # The "before" of the last row on a page comes from the next page.
    first_page = client.get(spot(item) + '/history', params={'size': 1, 'page': 0}).json()
    assert first_page['totalPages'] == 3 and len(first_page['items']) == 1
    assert first_page['items'][0]['before']['spotDescription'] == 'Desk A'
    last_page = client.get(spot(item) + '/history', params={'size': 1, 'page': 2}).json()
    assert last_page['items'][0]['before'] is None
    beyond = client.get(spot(item) + '/history', params={'size': 1, 'page': 3}).json()
    assert beyond['items'] == [] and beyond['totalElements'] == 3


def test_change_with_a_storage_photo(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'with photo')
    photo = upload(client, headers, purpose='DROP_OFF').json()['photoId']

    response = put(client, item, headers, **{**desk(body), 'photo': {'photoId': photo, 'altText': 'desk'}})
    assert response.status_code == 200, response.text
    assert response.json()['photo'] == {'photoId': photo, 'altText': 'desk', 'accessRequiresLogin': True}
    # Storage photos stay out of the item's own photo list.
    assert len(client.get(f"{BASE}/{item['itemId']}").json()['photos']) == 1

    count = revisions(env, item)
    again = {**desk(body), 'photo': {'photoId': photo, 'altText': 'again'}}
    error(put(client, item, headers, **again), 409, 'PHOTO_ALREADY_ATTACHED')
    item_photo = upload(client, headers).json()['photoId']
    error(put(client, item, headers, **{**desk(body), 'photo': {'photoId': item_photo, 'altText': 'x'}}),
          400, 'INVALID_REFERENCE')
    other = member(client, 'faculty-01')
    foreign = upload(client, other, purpose='DROP_OFF').json()['photoId']
    headers = member(client, 'student-01')
    error(put(client, item, headers, **{**desk(body), 'photo': {'photoId': foreign, 'altText': 'x'}}),
          403, 'PHOTO_FORBIDDEN')
    assert revisions(env, item) == count  # every failed change rolled back its new revision


@pytest.mark.parametrize('case', [
    'empty', 'no_building', 'no_spot', 'kept_with_building', 'kept_with_null_photo', 'bad_mode',
    'blank_spot', 'long_spot', 'extra_field',
])
def test_change_rejects_invalid_bodies(context, case):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'strict')
    building = body['foundBuildingId']
    payloads = {
        'empty': {},
        'no_building': {'mode': 'DROP_OFF', 'spotDescription': 'x'},
        'no_spot': {'mode': 'DROP_OFF', 'buildingId': building},
        'kept_with_building': {'mode': 'KEPT_BY_FINDER', 'buildingId': building},
        'kept_with_null_photo': {'mode': 'KEPT_BY_FINDER', 'photo': None},
        'bad_mode': {'mode': 'NOPE'},
        'blank_spot': desk(body, ' '),
        'long_spot': desk(body, 'x' * 301),
        'extra_field': {**desk(body), 'status': 'EXPIRED'},
    }

    error(put(client, item, headers, **payloads[case]), 400, 'VALIDATION_ERROR')
    assert revisions(env, item) == 1


def test_change_reference_rules(context):
    client, env, body, headers, storage = context
    item = located(client, body, headers)
    other = other_building(env)
    run(env, 'UPDATE buildings SET active=false WHERE id=:id', id=other)

    error(put(client, item, headers, **{**desk(body), 'buildingId': str(other)}), 400, 'INVALID_REFERENCE')
    error(put(client, item, headers, **{**desk(body), 'buildingId': str(uuid4())}), 400, 'INVALID_REFERENCE')

    # The building already used by the current spot may stay even once it is inactive.
    run(env, 'UPDATE buildings SET active=false WHERE id=:id', id=body['foundBuildingId'])
    assert put(client, item, headers, **desk(body, 'Desk B')).status_code == 200
    assert revisions(env, item) == 2


def test_change_authorization(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'mine')

    other = member(client, 'faculty-01')
    error(put(client, item, other, **desk(body)), 403, 'FORBIDDEN')
    admin = member(client, 'admin-01')
    error(put(client, item, admin, **desk(body)), 403, 'FORBIDDEN')
    guest(client)
    error(client.put(spot(item), json=desk(body)), 401, 'AUTH_REQUIRED')

    headers = member(client, 'student-01')
    error(client.put(spot(item), json=desk(body)), 403, 'CSRF_INVALID')
    error(client.put(spot(item), content='{}', headers={**headers, 'Content-Type': 'text/plain'}),
          415, 'UNSUPPORTED_MEDIA_TYPE')
    error(client.put(f'{BASE}/{uuid4()}/drop-off', json=desk(body), headers=headers), 404, 'NOT_FOUND')
    assert revisions(env, item) == 1


def test_sensitive_change_is_protected_and_audited(context):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'vault', categoryId=str(sensitive_category(env)))

    assert put(client, item, headers, **desk(body, 'PRIVATE STORAGE')).status_code == 200
    assert scalar(env, 'SELECT sensitive_latched FROM drop_off_versions WHERE item_id=:id AND revision_no=2',
                  id=item['itemId'])
    assert audits(env, item, 'DROP_OFF_CHANGED') == 2
    assert audits(env, item, 'SENSITIVE_DROP_OFF_VIEWED') == 1  # the response shows the spot


# ------------------------------------------------------------------ ITEM-08

def test_history_is_members_only_and_audited_for_sensitive_items(context):
    client, env, body, headers, storage = context
    plain = located(client, body, headers, 'plain')
    vault = located(client, body, headers, 'vault', categoryId=str(sensitive_category(env)))

    member(client, 'faculty-01')
    assert client.get(spot(plain) + '/history').status_code == 200
    assert audits(env, plain, 'SENSITIVE_DROP_OFF_VIEWED') == 0
    assert client.get(spot(vault) + '/history').status_code == 200
    assert client.get(spot(vault) + '/history').status_code == 200
    assert audits(env, vault, 'SENSITIVE_DROP_OFF_VIEWED') == 2

    guest(client)
    error(client.get(spot(plain) + '/history'), 401, 'AUTH_REQUIRED')


@pytest.mark.parametrize('params', [{'size': 0}, {'size': 101}, {'page': -1}, {'page': 'x'}, {'unknown': 1}])
def test_history_rejects_invalid_parameters(context, params):
    client, env, body, headers, storage = context
    item = add_item(client, body, headers, 'paged')
    error(client.get(spot(item) + '/history', params=params), 400, 'VALIDATION_ERROR')


def test_openapi_has_no_501_for_drop_off_operations(context):
    client, env, body, headers, storage = context
    paths = client.get('/openapi.json').json()['paths']
    for path, method in (('/drop-off', 'get'), ('/drop-off', 'put'), ('/drop-off/history', 'get')):
        operation = paths[BASE + '/{itemId}' + path][method]
        assert '501' not in operation['responses'] and operation['responses']['200']


@pytest.mark.parametrize('read', ['current', 'history'])
def test_drop_off_reads_do_not_expose_a_location_added_after_hiding(context, monkeypatch, read):
    client, env, body, headers, storage = context
    item = located(client, body, headers)
    member(client, 'faculty-01')  # neither the finder nor an administrator
    url = spot(item) + ('/history' if read == 'history' else '')

    def hide_and_move():
        with env.sync.begin() as db:
            db.execute(text('UPDATE found_items SET hidden=true WHERE id=:id'), {'id': item['itemId']})
            db.execute(text(
                'INSERT INTO drop_off_versions (id,item_id,revision_no,mode,building_id,spot_description,'
                'changed_by_user_id,changed_at) SELECT gen_random_uuid(),item_id,revision_no+1,mode,building_id,'
                "'Added after hiding',changed_by_user_id,now() FROM drop_off_versions WHERE item_id=:id "
                'ORDER BY revision_no DESC LIMIT 1'), {'id': item['itemId']})

    race = {}
    original = FoundItemService.load

    async def load_then_compete(self, *args, **kwargs):
        found = await original(self, *args, **kwargs)
        if 'thread' not in race:
            race['thread'] = threading.Thread(target=hide_and_move)
            race['thread'].start()
            await asyncio.sleep(1)  # long enough for the competing commit unless the row is locked
            race['committed_meanwhile'] = not race['thread'].is_alive()
        return found

    monkeypatch.setattr(FoundItemService, 'load', load_then_compete)
    response = client.get(url)
    race['thread'].join(timeout=15)

    assert not race['thread'].is_alive()
    # Either the request finished first (old spot) or it saw the hidden item (404); never the new spot.
    assert 'Added after hiding' not in response.text
    assert response.status_code in {200, 404}
    assert race['committed_meanwhile'] is False  # the hide had to wait for this read
