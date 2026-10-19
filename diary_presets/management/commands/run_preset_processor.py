"""Run the existing OSS processor as a separately managed local process."""
import os
import runpy
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from diary_presets.processor_runtime import configuration_error


class Command(BaseCommand):
    help = '本机运行手帐资源处理 Worker（独立进程，不占用 Celery）'

    def handle(self, *args, **options):
        if not settings.DIARY_PRESETS_LOCAL_PROCESSOR_ENABLED:
            raise CommandError('未启用 DIARY_PRESETS_LOCAL_PROCESSOR_ENABLED')
        error = configuration_error(settings)
        if error:
            raise CommandError(error)
        for key in ('DIARY_PRESETS_PROCESSOR_TOKEN', 'ALIYUN_ACCESS_KEY_ID',
                    'ALIYUN_ACCESS_KEY_SECRET', 'ALIYUN_OSS_BUCKET',
                    'DIARY_PRESETS_OSS_PREFIX', 'PRESET_CONTROL_URL'):
            os.environ[key] = str(getattr(settings, key))
        # A workstation uses the public endpoint; the standalone cloud worker
        # retains its internal endpoint default.
        os.environ.setdefault('PRESET_WORKER_OSS_ENDPOINT', settings.ALIYUN_OSS_ENDPOINT)
        os.environ['PRESET_WORKER_HEALTH_FILE'] = str(settings.BASE_DIR / 'run/preset_processor.health.json')
        runpy.run_path(str(settings.BASE_DIR / 'deployment/preset-processor/worker.py'), run_name='__main__')
