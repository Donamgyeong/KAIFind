"""Mock provider with durable idempotency receipts and no external delivery."""

from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert

from model import MockEmailReceipt


class DeliveryError(Exception):
    def __init__(self, code, *, permanent=False, unknown=False):
        self.code, self.permanent, self.unknown = code, permanent, unknown


@dataclass(frozen=True)
class EmailMessage:
    delivery_id: object
    recipient: str
    subject: str
    text: str


class MockEmailProvider:
    def __init__(self, factory, clock):
        self.factory, self.clock = factory, clock

    async def lookup(self, delivery_id):
        async with self.factory() as db:
            receipt = await db.get(MockEmailReceipt, delivery_id)
            return str(delivery_id) if receipt else None

    async def send(self, message):
        async with self.factory() as db, db.begin():
            await db.execute(insert(MockEmailReceipt).values(
                delivery_id=message.delivery_id, accepted_at=self.clock(),
            ).on_conflict_do_nothing(index_elements=['delivery_id']))
        return str(message.delivery_id)
