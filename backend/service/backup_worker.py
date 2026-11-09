"""One dedicated thread keeps pg_dump and object storage off the event loop."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

from service.database_backup import utcnow


logger = logging.getLogger(__name__)


class BackupWorker:
    def __init__(self, service):
        self.service = service
        self.startup = utcnow()
        self.stop = asyncio.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='database-backup')
        self.task = None

    async def run(self):
        loop = asyncio.get_running_loop()
        while not self.stop.is_set():
            try:
                await loop.run_in_executor(
                    self.executor, lambda: self.service.run_once(startup=self.startup),
                )
            except Exception:
                logger.error('BACKUP_WORKER_CYCLE_FAILED')
            try:
                await asyncio.wait_for(self.stop.wait(), self.service.settings.poll_seconds)
            except asyncio.TimeoutError:
                pass

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.stop.set()
        if self.task:
            await self.task
        self.executor.shutdown(wait=False)
