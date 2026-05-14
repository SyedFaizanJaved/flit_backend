"""
Management command: close_expired_jobs
======================================
Auto-close active Job rows whose applicationDeadline has passed. Replaces the
former read-side-effect inside JobViewSet.get_queryset() (Bug #23).

Schedule via cron / Celery beat / systemd timer:

    python manage.py close_expired_jobs
    python manage.py close_expired_jobs --dry-run   # preview only
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
        today = timezone.now().date()

        expired = Job.objects.filter(status='active', applicationDeadline__date__lt=today)
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
                try:
                    notifier._call_ml_metadata_api(job)
                except Exception as e:
                    logger.exception(
                        "ML metadata notify failed for job %s: %s", job.id, e
                    )
                closed += 1
            except Exception as e:
                logger.exception("Failed to close job %s: %s", job.id, e)

        self.stdout.write(self.style.SUCCESS(f"Done. Closed: {closed}/{count}"))
