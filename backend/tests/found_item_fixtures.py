"""Shared fixtures and helpers for the found-item read/write contract tests.

Pytest resolves fixtures per module, so each test module imports the fixture names from
here. This file is not collected as a test module itself.
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from test_analysis_worker import analysis_env  # noqa: F401
from test_found_item_contract import BASE, context  # noqa: F401
from test_photo_contract import error, login, storage, upload  # noqa: F401


ME = '/api/v1/me/found-items'
SUMMARY_KEYS = {
    'itemId', 'category', 'title', 'status', 'foundBuilding', 'foundAt', 'createdAt',
    'photos', 'sensitive', 'hidden',
}
DETAIL_KEYS = SUMMARY_KEYS | {
    'description', 'analysisStatus', 'foundLocationDescription', 'finder', 'updatedAt',
    'postedAt', 'expiresAt', 'closedAt',
}


def add_item(client, body, headers, title='item', **changes):
    """Upload a fresh photo, register an item and return its JSON; kwargs override body fields."""
    photo = upload(client, headers)
    assert photo.status_code == 201, photo.text
    payload = {
        **body, 'title': title,
        'photos': [{'photoId': photo.json()['photoId'], 'altText': title + ' photo'}],
        **changes,
    }
    response = client.post(BASE, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def run(env, statement, **params):
    with env.sync.begin() as db:
        db.execute(text(statement), params)


def scalar(env, statement, **params):
    with env.sync.connect() as db:
        return db.execute(text(statement), params).scalar_one()


def space_out(env, items):
    """The test clock is frozen; give items increasing created_at so ordering is observable."""
    for minutes, item in enumerate(items):
        run(env, 'UPDATE found_items SET created_at = :at WHERE id = :id',
            at=env.clock() + timedelta(minutes=minutes), id=item['itemId'])


def three_items(context):
    """first/second/third for the signed-in member, oldest to newest."""
    client, env, body, headers, storage = context
    items = [add_item(client, body, headers, title) for title in ('first', 'second', 'third')]
    space_out(env, items)
    return items


def close(env, item, status):
    run(env, 'UPDATE found_items SET status=:status, closed_at=:now, purge_after=:later WHERE id=:id',
        status=status, now=env.clock(), later=env.clock() + timedelta(days=365), id=item['itemId'])


def other_building(env):
    building = uuid4()
    run(env, "INSERT INTO buildings (id,code,name_ko,name_en) VALUES (:id,:code,'다른 건물','Other')",
        id=building, code=building.hex)
    return building


def sensitive_category(env):
    category = uuid4()
    run(env, "INSERT INTO categories (id,name_ko,name_en,sensitive) VALUES (:id,'민감','Sensitive',true)",
        id=category)
    return category


def titles(response):
    assert response.status_code == 200, response.text
    return [item['title'] for item in response.json()['items']]


def guest(client):
    client.cookies.clear()


def member(client, key):
    """Switch the client to another mock account and return its CSRF headers."""
    return login(client, key)[1]
