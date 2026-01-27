"""
Reset PostgreSQL sequences so new IDs start after existing data.
Use after pg_dump/restore ya jab bhi "duplicate key (id)=X already exists" aaye.

Usage:
    python manage.py reset_sequences
"""
from django.core.management.base import BaseCommand
from django.db import connection

# (table_name, id_column)
TABLES = [
    ('candidate_experience', 'id'),
    ('candidate_education', 'id'),
    ('candidate_achievements', 'id'),
]


class Command(BaseCommand):
    help = (
        'Sequences ko MAX(id) par set karta hai – '
        'naye rows ko last id ke baad wali id milti hai. Dump/restore ke baad chalao.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Sirf SQL dikhao, run mat karo.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write('Dry run – koi change nahi hoga.\n')

        with connection.cursor() as cursor:
            for table, col in TABLES:
                cursor.execute(
                    "SELECT pg_get_serial_sequence(%s, %s);",
                    [table, col],
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    self.stdout.write(
                        self.style.WARNING(f'{table}.{col}: koi sequence nahi mili, skip.')
                    )
                    continue
                seq = row[0]
                # next id = MAX(id)+1 => setval(seq, MAX(id))
                sql = f"SELECT setval(%s, COALESCE((SELECT MAX({col}) FROM {table}), 1));"
                if dry_run:
                    cursor.execute(f"SELECT COALESCE(MAX({col}), 0) FROM {table};")
                    mx = cursor.fetchone()[0]
                    self.stdout.write(f"-- {table}: max(id)={mx}, next id={mx+1}\n")
                    self.stdout.write(f"-- {sql % (repr(seq),)}\n")
                else:
                    try:
                        cursor.execute(sql, [seq])
                        cursor.execute(f"SELECT COALESCE(MAX({col}), 0) FROM {table};")
                        mx = cursor.fetchone()[0]
                        self.stdout.write(self.style.SUCCESS(f'{table}: sequence set, max(id)={mx}, next id={mx+1}'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'{table}: {e}'))

        if not dry_run:
            self.stdout.write(self.style.SUCCESS('\nSequences update ho gayi. Ab naye IDs last id ke baad se milengi.'))
