"""
Re-point PostgreSQL primary key sequences at the highest existing id.

Importing rows that carry explicit primary keys (loaddata, a SQL dump, or the
Supabase table editor) does not advance the sequence, so the next INSERT reuses
an id that is already taken and fails with a duplicate key error. Running this
once after such an import puts every sequence back in step.
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection


class Command(BaseCommand):
    help = 'Reset PostgreSQL primary key sequences to match the data already in the tables.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print the statements without running them.',
        )

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            self.stdout.write(self.style.WARNING(
                f'Database vendor is "{connection.vendor}"; sequences only need '
                'resetting on PostgreSQL. Nothing to do.'
            ))
            return

        statements = connection.ops.sequence_reset_sql(no_style(), list(apps.get_models()))
        if not statements:
            self.stdout.write('No sequences to reset.')
            return

        if options['dry_run']:
            for statement in statements:
                self.stdout.write(statement)
            self.stdout.write(self.style.WARNING(f'{len(statements)} statements (dry run, nothing applied).'))
            return

        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

        self.stdout.write(self.style.SUCCESS(f'Reset {len(statements)} sequences.'))
