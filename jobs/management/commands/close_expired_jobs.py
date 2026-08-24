"""
Management command: close_expired_jobs
======================================
Auto-close active Job rows whose applicationDeadline has passed. Replaces the
former read-side-effect inside JobViewSet.get_queryset() (Bug #23).

    python manage.py close_expired_jobs
    python manage.py close_expired_jobs --dry-run   # preview only

Scheduled by `manage.py run_expiry_scheduler`, which runs as its own systemd
service (deploy/flit-expiry-scheduler.service) and sweeps hourly. Run it directly for
a manual backfill:

    python manage.py close_expired_jobs

This is housekeeping, not the mechanism: candidate-facing lists and the apply guard
read JobQuerySet.open() live, so deadlines are honoured even if this never runs. All
this does is bring the stored `status` into line and drop the posting from the
ML vector store so it stops being ranked.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from jobs.models import Job
from jobs.views import JobMLMixin

logger = logging.getLogger(__name__)


class _MLNotifier(JobMLMixin):
    """Minimal carrier for the ML mixin so we can call its methods off the view."""
    pass


class Command(BaseCommand):
    help = "Close active jobs whose applicationDeadline is in the past."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without writing to the database or calling ML.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Read through the shared rule rather than repeating the lookup, so this
        # command and the live JobQuerySet.open() filter can never disagree.
        expired = Job.objects.expired()
        count = expired.count()
        self.stdout.write(self.style.NOTICE(
            f"[{timezone.now():%Y-%m-%d %H:%M:%S}] Found {count} expired active job(s) "
            f"{'(DRY RUN)' if dry_run else ''}"
        ))

        if dry_run or count == 0:
            for job in expired.iterator():
                self.stdout.write(f"  [DRY] Would close job {job.id} ({job.title})")
            self.stdout.write(self.style.SUCCESS(f"Done. Would close: {count}"))
            return

        notifier = _MLNotifier()
        closed = 0
        for job in expired.iterator():
            try:
                with transaction.atomic():
                    job.status = 'closed'
                    job.save(update_fields=['status'])
                # Drop it from the ML vector store. Updating metadata is not enough:
                # the record stays indexed and keeps getting ranked, which is what had
                # closed jobs still being recommended to candidates. Best-effort --
                # the row is already closed, and candidate-facing reads filter on
                # JobQuerySet.open() regardless, so a failure here costs a wasted
                # ranking slot, not a wrong result.
                try:
                    ok, error = notifier._call_ml_delete_api(job)
                    if not ok:
                        logger.error(
                            "ML delete failed for job %s: %s", job.id, error
                        )
                except Exception as e:
                    logger.exception(
                        "ML delete raised for job %s: %s", job.id, e
                    )
                closed += 1
            except Exception as e:
                logger.exception("Failed to close job %s: %s", job.id, e)

        self.stdout.write(self.style.SUCCESS(f"Done. Closed: {closed}/{count}"))
