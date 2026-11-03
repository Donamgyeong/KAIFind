"""PostgreSQL integration checks; run against a migrated disposable database.

TEST_DATABASE_URL must name a database beginning with kaifind_test_.
All test data is rolled back. No create_all or SQLite substitutes are used.
"""
import os
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from model import (Base, Building, Category, Collection, Conversation, DropOffVersion,
                   EmailDelivery, FoundItem, LostReport, LostReportPrivateDetail,
                   Message, Photo, PhotoAttachment, User)

NOW = datetime.now(timezone.utc)


@pytest.fixture(scope='session')
def engine():
    raw = os.getenv('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('TEST_DATABASE_URL is required for PostgreSQL schema tests')
    url = make_url(raw).set(drivername='postgresql+psycopg')
    if not url.database.startswith('kaifind_test_'):
        raise RuntimeError('Schema tests require a disposable kaifind_test_* database')
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def seed(db):
    finder, member, outsider, category, building, item = [uuid4() for _ in range(6)]
    for uid in (finder, member, outsider):
        db.execute(insert(User).values(id=uid, mock_subject=str(uid), name='Test',
                                      email='test@example.com', affiliation='STUDENT'))
    db.execute(insert(Category).values(id=category, name_ko='물품', name_en='Item'))
    db.execute(insert(Building).values(id=building, code=str(building), name_ko='건물', name_en='Building'))
    db.execute(insert(FoundItem).values(id=item, finder_id=finder, category_id=category,
        found_building_id=building, title='Item', description='Description',
        found_location_description='Lobby', found_at=NOW, expires_at=NOW+timedelta(days=30)))
    return dict(finder=finder, member=member, outsider=outsider, category=category, building=building, item=item)


def test_schema_matches_migrated_database(db):
    names = set(db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'" )).scalars())
    assert set(Base.metadata.tables) <= names
    assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20261103_0003'


def test_single_active_collector_and_new_collection_after_undo(db, seed):
    def collect():
        return insert(Collection).values(id=uuid4(), item_id=seed['item'], finder_id=seed['finder'],
            collector_id=seed['member'], purge_after=NOW+timedelta(days=365))
    db.execute(collect())
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(collect())
    db.execute(update(Collection).values(undone_at=NOW, undone_by_user_id=seed['finder']))
    db.execute(collect())
    assert len(db.execute(select(Collection.id)).all()) == 2


def test_email_slot_and_digest_limits(db, seed):
    values = dict(recipient_id=seed['member'], delivery_date=date.today(), kind='INDIVIDUAL', slot_no=1)
    db.execute(insert(EmailDelivery).values(id=uuid4(), **values))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(EmailDelivery).values(id=uuid4(), **values))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(EmailDelivery).values(id=uuid4(), **{**values, 'slot_no':20}))
    db.execute(insert(EmailDelivery).values(id=uuid4(), **{**values, 'slot_no':20, 'kind':'DIGEST'}))


def report(db, seed):
    rid = uuid4()
    db.execute(insert(LostReport).values(id=rid, owner_id=seed['member'], category_id=seed['category'],
        description='Lost', lost_date_from=date.today(), lost_date_to=date.today(),
        expires_at=NOW+timedelta(days=30)))
    return rid


def test_open_report_requires_private_details_at_commit(db, seed):
    with pytest.raises(IntegrityError), db.begin_nested():
        report(db, seed)
        db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))


def test_report_closure_erases_private_details_and_cannot_reopen(db, seed):
    rid = report(db, seed)
    db.execute(insert(LostReportPrivateDetail).values(report_id=rid, details='Private mark'))
    db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    db.execute(update(LostReport).where(LostReport.id==rid).values(status='CLOSED', closed_at=NOW))
    assert db.execute(select(LostReportPrivateDetail.report_id)).first() is None
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(LostReportPrivateDetail).values(report_id=rid, details='Restored'))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(LostReport).where(LostReport.id==rid).values(status='OPEN', closed_at=None))
    db.execute(update(LostReport).where(LostReport.id==rid).values(status='RESOLVED'))


def test_closed_item_erases_conversations_and_rejects_messages(db, seed):
    cid = uuid4()
    db.execute(insert(Conversation).values(id=cid, item_id=seed['item'], member_id=seed['member']))
    db.execute(insert(Message).values(id=uuid4(), conversation_id=cid, sender_id=seed['member'], content='Hello'))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(Message).values(id=uuid4(), conversation_id=cid, sender_id=seed['outsider'], content='No'))
    db.execute(update(FoundItem).where(FoundItem.id==seed['item']).values(status='EXPIRED', closed_at=NOW))
    assert db.execute(select(Conversation.id)).first() is None
    assert db.execute(select(Message.id)).first() is None
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(Conversation).values(id=uuid4(), item_id=seed['item'], member_id=seed['member']))


def test_photo_sensitivity_is_latched_and_purpose_checked(db, seed):
    photo = uuid4()
    db.execute(insert(Photo).values(id=photo, uploader_id=seed['finder'], purpose='ITEM',
        object_key=str(photo), content_type='image/jpeg', size_bytes=100, width=10, height=10))
    db.execute(insert(PhotoAttachment).values(photo_id=photo, item_id=seed['item'], alt_text='Item', display_order=0))
    sensitive = uuid4()
    db.execute(insert(Category).values(id=sensitive, name_ko='민감', name_en='Sensitive', sensitive=True))
    db.execute(update(FoundItem).where(FoundItem.id==seed['item']).values(category_id=sensitive))
    db.execute(update(FoundItem).where(FoundItem.id==seed['item']).values(category_id=seed['category']))
    assert db.execute(select(PhotoAttachment.sensitive_latched)).scalar_one() is True
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(PhotoAttachment).values(sensitive_latched=False))
    drop_photo = uuid4()
    db.execute(insert(Photo).values(id=drop_photo, uploader_id=seed['finder'], purpose='DROP_OFF',
        object_key=str(drop_photo), content_type='image/png', size_bytes=100, width=10, height=10))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(PhotoAttachment).values(photo_id=drop_photo, item_id=seed['item'], alt_text='Wrong', display_order=1))


def test_category_sensitivity_immutable(db, seed):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(Category).where(Category.id==seed['category']).values(sensitive=True))


def test_drop_off_history_is_immutable_and_shape_checked(db, seed):
    values = dict(id=uuid4(), item_id=seed['item'], revision_no=1, mode='KEPT_BY_FINDER', changed_by_user_id=seed['finder'])
    db.execute(insert(DropOffVersion).values(**values))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(DropOffVersion).values(mode='DROP_OFF', building_id=seed['building'], spot_description='Desk'))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(DropOffVersion).values(**{**values, 'id':uuid4(), 'revision_no':2, 'building_id':seed['building']}))


def test_collection_survives_item_deletion_for_independent_retention(db, seed):
    db.execute(insert(Collection).values(id=uuid4(), item_id=seed['item'], finder_id=seed['finder'],
        collector_id=seed['member'], purge_after=NOW+timedelta(days=365)))
    db.execute(delete(FoundItem).where(FoundItem.id==seed['item']))
    assert db.execute(select(Collection.item_id)).scalar_one() == seed['item']


def test_orm_optimistic_version_rejects_stale_edit(db, seed):
    from sqlalchemy.orm import Session as ORMSession
    from sqlalchemy.orm.exc import StaleDataError

    with ORMSession(bind=db, join_transaction_mode='create_savepoint') as session:
        item = session.get(FoundItem, seed['item'])
        db.execute(update(FoundItem).where(FoundItem.id==item.id).values(version=item.version+1))
        item.title = 'Stale edit'
        with pytest.raises(StaleDataError):
            session.flush()
        session.rollback()
