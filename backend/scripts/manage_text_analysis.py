"""Explicit initial activation, keyset reconciliation, and audited retry."""
import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from library.database import session_factory
from library.translation_runtime import TranslationRuntime, TranslationSettings
from service.text_analysis import KINDS
from service.text_analysis_maintenance import repair_batch, retry_failed
from service.text_analysis_profiles import initialize_policy


async def run(args):
    factory = session_factory()
    if args.command == 'initialize':
        runtime = TranslationRuntime(TranslationSettings.from_environment())
        try:
            await runtime.start()
            async with factory() as db, db.begin():
                await initialize_policy(db, runtime.profile, now=datetime.now(timezone.utc))
        finally:
            await runtime.close()
    elif args.command == 'repair':
        for kind in KINDS:
            after = None
            while True:
                async with factory() as db, db.begin():
                    after = await repair_batch(
                        db, kind=kind, now=datetime.now(timezone.utc), after=after,
                    )
                if after is None:
                    break
    else:
        async with factory() as db, db.begin():
            await retry_failed(db, event_id=args.event_id, now=datetime.now(timezone.utc))


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('Run inside the existing backend container')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('initialize')
    commands.add_parser('repair')
    retry = commands.add_parser('retry')
    retry.add_argument('event_id', type=UUID)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception:
        # Do not echo exception parameters or source text into operational logs.
        raise SystemExit('TEXT_ANALYSIS_MAINTENANCE_FAILED') from None


if __name__ == '__main__':
    main()
