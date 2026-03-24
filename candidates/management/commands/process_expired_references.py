"""
Management command: process_expired_references
================================================
Run daily (via cron / systemd timer) to auto-expire pending
ReferenceRequests whose 7-day expiry has passed.

Usage:
    python manage.py process_expired_references
    python manage.py process_expired_references --dry-run   # preview only
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from candidates.models import ReferenceRequest

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Mark pending reference requests as 'expired' if their "
        "7-day expiry date has passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without writing to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        self.stdout.write(
            self.style.NOTICE(
                f"[{now:%Y-%m-%d %H:%M:%S}] Starting reference expiry check "
                f"{'(DRY RUN)' if dry_run else ''}"
            )
        )

        # Find all pending requests whose expiry date has passed
        expired_candidates = ReferenceRequest.objects.filter(
            status='pending',
            expires_at__lt=now,
        )

        expired_count = 0
        for ref in expired_candidates:
            if dry_run:
                self.stdout.write(
                    f"  [DRY] Would mark #{ref.pk} ({ref.reference_email}) "
                    f"as expired (expired at {ref.expires_at})"
                )
                expired_count += 1
            else:
                marked = ref.mark_expired()
                if marked:
                    expired_count += 1
                    logger.info(
                        f"ReferenceRequest #{ref.pk} → {ref.reference_email} "
                        f"marked as expired"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Requests expired: {expired_count}"
            )
        )
