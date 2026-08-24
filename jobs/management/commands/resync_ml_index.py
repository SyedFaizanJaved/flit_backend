"""
Management command: resync_ml_index
===================================
One-time cleanup. The ML vector store still holds every posting that was closed before
delete-on-close existed -- statuses were flipped silently by the old read-side-effect
(Bug #23) and by JobViewSet.update_status, neither of which told ML anything. Those
records keep getting ranked, which is why candidates were shown dead postings.

This DELETEs every posting that is not currently open, so the index ends up holding
only what open() would return.

    python manage.py resync_ml_index --dry-run
    python manage.py resync_ml_index
    python manage.py resync_ml_index --entity jobs --start-id 148   # resume

Resumable by design: rows are walked in ascending id and the last id reached is printed
on exit, including on Ctrl+C. Feed it back via --start-id rather than restarting the
whole sweep. Not needed after the initial cleanup -- close_expired_* and update_status
keep the index in step from here on.
"""

import time

from django.core.management.base import BaseCommand, CommandError

from jobs.models import Job
from jobs.views import JobMLMixin
from projects.models import Project
from projects.views import ProjectMLMixin

# Paced rather than hammered: this walks ~600 rows against a service whose other calls
# run 2.6-4.2s, and nothing here is urgent.
DELAY_SECONDS = 0.2
PROGRESS_EVERY = 25


class _JobNotifier(JobMLMixin):
    pass


class _ProjectNotifier(ProjectMLMixin):
    pass


ENTITIES = {
    'jobs': (Job, _JobNotifier, 'job'),
    'projects': (Project, _ProjectNotifier, 'project'),
}


class Command(BaseCommand):
    help = "Delete every not-currently-open job/project from the ML vector store."

    def add_arguments(self, parser):
        parser.add_argument(
            '--entity', choices=['jobs', 'projects', 'all'], default='all',
            help='Which index to clean (default: all).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be deleted without calling ML.',
        )
        parser.add_argument(
            '--start-id', type=int, default=0,
            help='Skip ids below this. Use the id printed by a previous interrupted run.',
        )

    def handle(self, *args, **options):
        names = list(ENTITIES) if options['entity'] == 'all' else [options['entity']]
        if options['start_id'] and options['entity'] == 'all':
            raise CommandError("--start-id needs a single --entity; ids are per-table.")

        for name in names:
            self._resync(name, options['dry_run'], options['start_id'])

    def _resync(self, name, dry_run, start_id):
        model, notifier_cls, label = ENTITIES[name]

        # Everything open() would not return: closed, draft, paused, completed, and
        # active-but-past-deadline. Read through open() so this can never disagree with
        # what the candidate-facing endpoints actually show.
        stale = (
            model.objects.exclude(pk__in=model.objects.open().values('pk'))
            .filter(pk__gte=start_id)
            .order_by('pk')
        )
        total = stale.count()
        self.stdout.write(self.style.NOTICE(
            f"{name}: {total} not-open row(s) to remove from the ML index"
            f"{' (DRY RUN)' if dry_run else ''}"
        ))
        if dry_run or not total:
            return

        notifier = notifier_cls()
        deleted = failed = 0
        last_id = start_id
        try:
            for obj in stale.iterator():
                last_id = obj.pk
                ok, error = notifier._call_ml_delete_api(obj)
                if ok:
                    deleted += 1
                else:
                    failed += 1
                    self.stderr.write(f"  {label} {obj.pk}: {error}")
                if (deleted + failed) % PROGRESS_EVERY == 0:
                    self.stdout.write(f"  ...{deleted + failed}/{total} (at id {last_id})")
                time.sleep(DELAY_SECONDS)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING(
                f"\nInterrupted at {label} id {last_id}. Resume with:\n"
                f"    manage.py resync_ml_index --entity {name} --start-id {last_id + 1}"
            ))
            raise

        style = self.style.SUCCESS if not failed else self.style.WARNING
        self.stdout.write(style(
            f"{name}: deleted {deleted}/{total}, failed {failed}. Last id {last_id}."
        ))
        if failed:
            self.stdout.write(
                f"    Re-run to retry failures; deleting an absent record is a no-op."
            )
