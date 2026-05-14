"""
Management command: close_expired_projects
==========================================
Auto-close active Project rows whose deadline has passed. Replaces the
former read-side-effect inside ProjectViewSet.get_queryset() (Bug #23).

Schedule via cron / Celery beat / systemd timer:

    python manage.py close_expired_projects
    python manage.py close_expired_projects --dry-run   # preview only
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
        today = timezone.now().date()

        expired = Project.objects.filter(status='active', deadline__lt=today)
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
