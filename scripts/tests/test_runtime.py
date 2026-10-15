"""Process lifecycle checks without connecting to the application database."""
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runtime', Path(__file__).resolve().parents[1] / 'runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root_patch = patch.object(runtime, 'ROOT', Path(self.temp.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.run_patch = patch.object(runtime, 'RUN', Path(self.temp.name) / 'run')
        self.log_patch = patch.object(runtime, 'LOG', Path(self.temp.name) / 'logs')
        self.run_patch.start()
        self.log_patch.start()
        self.addCleanup(self.run_patch.stop)
        self.addCleanup(self.log_patch.stop)

    def test_start_is_idempotent_and_stop_terminates_only_owned_process(self):
        cmd = [sys.executable, '-c', 'import time; time.sleep(60)', str(runtime.ROOT)]
        with patch.object(runtime, 'command', return_value=cmd):
            runtime.start('celery_worker')
            pid = runtime.pid_for('celery_worker')
            self.addCleanup(lambda: runtime.stop('celery_worker'))
            runtime.start('celery_worker')
            self.assertEqual(runtime.pid_for('celery_worker'), pid)
            self.assertTrue(runtime.owned(pid))
            runtime.stop('celery_worker')
            self.assertFalse(runtime.owned(pid))
            self.assertIsNone(runtime.pid_for('celery_worker'))

    def test_stale_pid_does_not_kill_unrelated_process(self):
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.addCleanup(proc.wait)
        self.addCleanup(proc.terminate)
        runtime.RUN.mkdir()
        (runtime.RUN / 'frontend.pid').write_text(str(proc.pid))
        runtime.stop('frontend')
        self.assertIsNone(proc.poll())

    def test_occupied_port_is_reported_without_starting_or_killing_processes(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = str(listener.getsockname()[1])
            with patch.dict('os.environ', {'BACKEND_PORT': port}), patch.object(runtime.subprocess, 'Popen') as popen:
                with self.assertRaisesRegex(RuntimeError, '端口'):
                    runtime.start('backend')
                popen.assert_not_called()
                self.assertTrue(runtime.check_port(int(port)))


if __name__ == '__main__':
    unittest.main()
