"""List (and optionally delete) upload files that no database row references.

The API cleans up its own files — deleting a resume removes the original file and
the cropped avatar, deleting an avatar removes the old one, and deleting an
account removes everything. Files still become orphaned when rows are removed
outside the API (psql, a failed migration, an old SQLite database that was
replaced), which is exactly what this script is for.

Usage (inside the backend container):

    python scripts/prune_orphan_uploads.py            # dry run: print the list
    python scripts/prune_orphan_uploads.py --delete   # remove the listed files
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import async_session  # noqa: E402
from app.models.resume import Resume  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.storage import stored_filename  # noqa: E402


async def collect_orphans() -> tuple[list[str], list[str]]:
    """Return (referenced, orphans) filenames found in UPLOAD_DIR."""
    settings = get_settings()
    upload_dir = settings.UPLOAD_DIR

    referenced: set[str] = set()
    async with async_session() as session:
        for column in (Resume.original_file_url, Resume.avatar_url, User.avatar_url):
            for (value,) in (await session.execute(select(column))).all():
                if value:
                    referenced.add(stored_filename(value))

    on_disk = {
        name
        for name in os.listdir(upload_dir)
        if os.path.isfile(os.path.join(upload_dir, name))
    }
    return sorted(referenced), sorted(on_disk - referenced)


def prune(orphans: list[str]) -> int:
    """Delete the given filenames from UPLOAD_DIR; returns how many were removed."""
    upload_dir = get_settings().UPLOAD_DIR
    removed = 0
    for name in orphans:
        # Never let a crafted name escape the upload directory.
        if os.path.dirname(os.path.normpath(os.path.join(upload_dir, name))) != os.path.normpath(upload_dir):
            print(f"  skipped (outside upload dir): {name}")
            continue
        try:
            os.remove(os.path.join(upload_dir, name))
            removed += 1
        except OSError as exc:
            print(f"  failed to remove {name}: {exc}")
    return removed


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="actually delete the orphaned files (default is a dry run)",
    )
    args = parser.parse_args()

    referenced, orphans = await collect_orphans()
    print(f"referenced by the database : {len(referenced)}")
    print(f"orphaned on disk           : {len(orphans)}")
    for name in orphans:
        print(f"  {name}")

    if not args.delete:
        print("\nDry run — nothing was deleted. Re-run with --delete to remove them.")
        return

    removed = prune(orphans)
    print(f"\nRemoved {removed} of {len(orphans)} orphaned file(s).")


if __name__ == "__main__":
    asyncio.run(main())
