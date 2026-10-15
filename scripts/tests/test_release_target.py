"""Verify target isolation with a fake SSH client; never connect to a server."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / 'scripts/deploy_sparkservice.sh'


class ReleaseTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.trace = folder / 'ssh-calls'
        fake = folder / 'ssh'
        fake.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$SSH_TRACE"\nif [[ "$1" != "-G" ]]; then exit 99; fi\nprintf "hostname %s\\n" "${TEST_SSH_HOSTNAME:-39.106.39.110}"\n')
        fake.chmod(0o755)
        self.env = {**os.environ, 'PATH': f'{folder}:{os.environ["PATH"]}', 'SSH_TRACE': str(self.trace), 'SRC_DIR': str(ROOT), 'REMOTE_HOST': 'root@39.106.39.110'}

    def run_entry(self, **overrides):
        return subprocess.run(['bash', str(ENTRY), '--check-target'], env={**self.env, **overrides}, capture_output=True, text=True)

    def test_current_target_passes_without_remote_connection(self):
        result = self.run_entry()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trace.read_text().strip(), '-G root@39.106.39.110')

    def test_legacy_target_is_blocked_before_ssh(self):
        result = self.run_entry(REMOTE_HOST='root@139.196.215.51')
        self.assertEqual(result.returncode, 2)
        self.assertIn('严禁', result.stderr)
        self.assertFalse(self.trace.exists())

    def test_alias_and_other_address_are_blocked(self):
        for target in ['legacy-server', 'root@192.0.2.1', '-oProxyCommand=bad']:
            with self.subTest(target=target):
                self.assertEqual(self.run_entry(REMOTE_HOST=target).returncode, 2)
        self.assertFalse(self.trace.exists())

    def test_ssh_hostname_override_to_old_server_is_blocked(self):
        result = self.run_entry(TEST_SSH_HOSTNAME='139.196.215.51')
        self.assertEqual(result.returncode, 2)
        self.assertIn('SSH HostName', result.stderr)
        self.assertEqual(len(self.trace.read_text().splitlines()), 1)

    def test_skill_remote_checks_reject_old_target_before_connecting(self):
        for name in ['release_preflight.sh', 'post_release_audit.sh']:
            entry = Path('/Users/dream/Documents/Skill/发版/scripts') / name
            if not entry.exists():
                self.skipTest('Personal release skill is not installed in this environment')
            args = ['bash', str(entry)] + (['--remote'] if name == 'release_preflight.sh' else [])
            result = subprocess.run(args, env={**self.env, 'SPARK_SOURCE_DIR': str(ROOT),
                'REMOTE_TARGET': 'root@139.196.215.51'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.trace.exists())

    def test_unknown_source_branch_is_blocked(self):
        result = self.run_entry(SRC_DIR=self.temp.name)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.trace.exists())


if __name__ == '__main__':
    unittest.main()
