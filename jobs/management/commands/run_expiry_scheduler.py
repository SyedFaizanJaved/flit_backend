"""
Management command: run_expiry_scheduler
========================================
Long-running scheduler that drives both expiry sweeps. Replaces the crontab entries
the close_expired_* docstrings describe, so the schedule lives in the repo and gets
reviewed like any other code.

    python manage.py run_expiry_scheduler        # loop until SIGTERM
    python manage.py run_expiry_scheduler --once # one sweep, then exit

Run it as its own systemd service (deploy/flit-expiry-scheduler.service), NOT from
inside Django. Gunicorn runs several workers and daphne is a further process; a
scheduler started in AppConfig.ready() or middleware would exist once per worker,
so every sweep would run N times over the same rows and fire N duplicate ML PATCHes.
One process, one scheduler.

Wakes at :05 past every hour rather than once a day. Expiry is currently date-granular
(see JobQuerySet), so most sweeps find nothing and cost two indexed counts -- what the
hourly cadence buys is recovery time: if the box was down at midnight, the backlog
clears within the hour instead of waiting a full day.
"""

import logging
import signal
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

SWEEPS = ('close_expired_jobs', 'close_expired_projects')

INTERVAL_SECONDS = 3600
OFFSET_SECONDS = 300  # :05 past the hour, matching the crontab this replaces

# Coarse enough to cost nothing, fine enough that systemd never has to SIGKILL us
# (its default TimeoutStopSec is 90s).
SHUTDOWN_POLL_SECONDS = 5


def seconds_until_next_run(now_ts, interval=INTERVAL_SECONDS, offset=OFFSET_SECONDS):
    """Seconds from `now_ts` (a POSIX timestamp) to the next interval boundary + offset.

    Anchored to the epoch rather than to start-up, so restarts don't drift the schedule
    and two hosts stay in step. Returns a full interval when called exactly on a
    boundary, so a sweep never immediately repeats itself.
    """
    return interval - ((now_ts - offset) % interval)


class Command(BaseCommand):
    help = "Continuously close jobs and projects whose deadline has passed."

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run a single sweep immediately and exit (useful for backfills).',
        )

    def handle(self, *args, **options):
        self._stop = False
        signal.signal(signal.SIGTERM, self._request_stop)
        signal.signal(signal.SIGINT, self._request_stop)

        if options['once']:
            self._sweep()
            return

        self.stdout.write(self.style.SUCCESS(
            f"Expiry scheduler started; sweeping every {INTERVAL_SECONDS}s "
            f"at +{OFFSET_SECONDS}s past the boundary."
        ))
        while not self._stop:
            self._sleep_until_next_run()
            if self._stop:
                break
            self._sweep()
        self.stdout.write(self.style.NOTICE("Expiry scheduler stopped."))

    def _request_stop(self, signum, frame):
        self._stop = True

    def _sleep_until_next_run(self):
        # Sliced rather than one long sleep: PEP 475 makes time.sleep resume after a
        # signal handler returns, so a single sleep(3600) would ignore SIGTERM for up
        # to an hour and systemd would end up SIGKILLing us mid-sweep.
        deadline = time.monotonic() + seconds_until_next_run(time.time())
        while not self._stop:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(SHUTDOWN_POLL_SECONDS, remaining))

    def _sweep(self):
        self.stdout.write(self.style.NOTICE(f"[{timezone.now():%Y-%m-%d %H:%M:%S}] Sweeping..."))
        for command in SWEEPS:
            try:
                call_command(command)
            except Exception:
                # A failing sweep must not kill the process or skip its sibling --
                # systemd would restart us, and we would then wait a full interval
                # before trying again.
                logger.exception("Expiry sweep %s failed", command)
