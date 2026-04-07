"""
Test pending migrations against a copy of the production database.

Catches data-migration conflicts (NOT NULL violations, constraint failures,
etc.) that Django's test suite misses because tests run on empty databases.

Usage:
    python3 manage.py preflight_migrate              # test against ./db.sqlite3
    python3 manage.py preflight_migrate --db /path/to/prod.sqlite3  # explicit path

Run BEFORE deploying. If this passes, `manage.py migrate` will succeed on prod.
"""

import shutil
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Test pending migrations against a copy of the database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--db',
            default=None,
            help='Path to the SQLite database to test against (default: project db.sqlite3)',
        )

    def handle(self, *args, **options):
        db_path = options['db'] or settings.DATABASES['default']['NAME']

        self.stdout.write(f"Copying {db_path} to temp file...")
        tmp = tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False)
        tmp.close()
        shutil.copy2(str(db_path), tmp.name)

        # Point the default connection at the copy
        old_name = settings.DATABASES['default']['NAME']
        settings.DATABASES['default']['NAME'] = tmp.name
        connections['default'].close()
        connections['default'].settings_dict['NAME'] = tmp.name

        try:
            self.stdout.write("Running migrations against the copy...")
            call_command('migrate', verbosity=1, stdout=self.stdout)
            self.stdout.write(self.style.SUCCESS("\nPREFLIGHT PASSED — migrations are safe to deploy."))
        except Exception as e:
            raise CommandError(
                f"\nPREFLIGHT FAILED — migration would fail on prod:\n\n{e}\n\n"
                f"Fix the data or migration before deploying."
            )
        finally:
            # Restore original DB path
            settings.DATABASES['default']['NAME'] = old_name
            connections['default'].close()
            connections['default'].settings_dict['NAME'] = old_name

            import os
            os.unlink(tmp.name)
            self.stdout.write(f"Temp file cleaned up.")
