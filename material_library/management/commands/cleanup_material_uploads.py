from django.core.management.base import BaseCommand
from material_library.lifecycle import cleanup_candidates, scan_cleanup, execute_cleanup


class Command(BaseCommand):
    help = '仅清理过期上传临时文件，正式资源始终保留；默认 dry-run'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7)
        parser.add_argument('--execute', action='store_true')

    def handle(self, *args, **options):
        if not options['execute']:
            self.stdout.write(f"dry-run: candidates={len(cleanup_candidates(options['days']))}; no files or database rows changed")
            return
        job = scan_cleanup(None, days=max(7, options['days']))
        if options['execute']:
            while job.state in ('preview', 'pending'):
                job = execute_cleanup(job.pk)
        completed = sum(e['state']=='deleted' for e in job.entries)
        self.stdout.write(f"job={job.pk} state={job.state} candidates={len(job.entries)} deleted={completed}")
