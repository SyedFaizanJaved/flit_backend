"""
Management command: close_expired_projects
==========================================
Auto-close active Project rows whose deadline has passed. Replaces the
former read-side-effect inside ProjectViewSet.get_queryset() (Bug #23).

Schedule via cron / Celery beat / systemd timer:

    python manage.py close_expired_projects
    python manage.py close_expired_projects --dry-run   # preview only

Scheduling: expiry is date-granular (see ProjectQuerySet), so state only changes at
00:00 UTC and a single daily run is sufficient. Add to the server crontab:

    5 0 * * * cd /path/to/flit_backend && /path/to/venv/bin/python manage.py close_expired_projects

This is housekeeping, not the mechanism: candidate-facing lists and the apply guard
read ProjectQuerySet.open() live, so deadlines are honoured even if this never runs.
All this does is bring the stored `status` into line and notify the ML service.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from projects.models import Project
from projects.views import ProjectMLMixin

logger = logging.getLogger(__name__)


class _MLNotifier(ProjectMLMixin):
    """Minimal carrier for the ML mixin so we can call its methods off the view."""
    pass


class Command(BaseCommand):
    help = "Close active projects whose deadline is in the past."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without writing to the database or calling ML.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Read through the shared rule rather than repeating the lookup, so this
        # command and the live ProjectQuerySet.open() filter can never disagree.
        expired = Project.objects.expired()
        count = expired.count()
        self.stdout.write(self.style.NOTICE(
            f"[{timezone.now():%Y-%m-%d %H:%M:%S}] Found {count} expired active project(s) "
            f"{'(DRY RUN)' if dry_run else ''}"
        ))

        if dry_run or count == 0:
            for project in expired.iterator():
                self.stdout.write(f"  [DRY] Would close project {project.id} ({project.title})")
            self.stdout.write(self.style.SUCCESS(f"Done. Would close: {count}"))
            return

        notifier = _MLNotifier()
        closed = 0
        for project in expired.iterator():
            try:
                with transaction.atomic():
                    project.status = 'closed'
                    project.save(update_fields=['status'])
                try:
                    notifier._call_ml_metadata_api(project)
                except Exception as e:
                    logger.exception(
                        "ML metadata notify failed for project %s: %s", project.id, e
                    )
                closed += 1
            except Exception as e:
                logger.exception("Failed to close project %s: %s", project.id, e)

        self.stdout.write(self.style.SUCCESS(f"Done. Closed: {closed}/{count}"))
