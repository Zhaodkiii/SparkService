"""Exercise release failures with temporary files and fake infrastructure only."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "deployment/server"
spec = importlib.util.spec_from_file_location("release_checks", TEMPLATE / "bin/release_checks.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def production_config(**overrides):
    return {
        "DJANGO_SECRET_KEY": "test-secret",
        "DB_HOST": "127.0.0.1",
        "DB_NAME": "sparkservice",
        "DB_USER": "traveldiary",
        "DB_PASSWORD": "test-password",
        "DJANGO_ALLOWED_HOSTS": "diary.dreamwhale.top,localhost",
        "CSRF_TRUSTED_ORIGINS": "https://diary.dreamwhale.top",
        "CORS_ALLOWED_ORIGINS": "https://diary.dreamwhale.top",
        "CELERY_BROKER_URL": "redis://127.0.0.1:6379/4",
        "CELERY_RESULT_BACKEND": "redis://127.0.0.1:6379/4",
        **overrides,
    }


class ReleaseConfigTests(unittest.TestCase):
    def test_production_config_passes(self):
        checks.validate_config(production_config())

    def test_root_with_password_passes(self):
        checks.validate_config(production_config(DB_USER="root"))

    def test_missing_password_and_wrong_environment_are_blocked(self):
        for overrides in (
            {"DB_USER": "root", "DB_PASSWORD": ""}, {"DB_PASSWORD": ""}, {"DB_HOST": "legacy.example"},
            {"DB_NAME": "mysql"}, {"DB_ENGINE": "django.db.backends.sqlite3"},
            {"DJANGO_ALLOWED_HOSTS": "legacy.example"}, {"DJANGO_PORT": "2026"},
            {"CELERY_BROKER_URL": "redis://legacy.example:6379/0"},
            {"CELERY_QUEUES": "celery, chat.ai"},
        ):
            with self.subTest(keys=list(overrides)), self.assertRaises(ValueError):
                checks.validate_config(production_config(**overrides))

    def test_env_duplicate_keys_are_rejected_and_password_is_literal(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / "candidate.env"
            env.write_text("DB_PASSWORD='literal${VALUE}#password'\n")
            self.assertEqual(checks.load_config(env)["DB_PASSWORD"], "literal${VALUE}#password")
            env.write_text("DB_USER=root\nDB_USER=traveldiary\n")
            with self.assertRaisesRegex(ValueError, "重复键"):
                checks.load_config(env)

    def test_bad_config_stops_before_build_or_network_and_hides_password(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            envfile = folder / "candidate.env"
            values = production_config(DB_USER="root", DB_HOST="legacy.example", DB_PASSWORD="must-not-appear")
            envfile.write_text("".join(f"{key}='{value}'\n" for key, value in values.items()))
            trace = folder / "trace"
            ssh = folder / "ssh"
            ssh.write_text('#!/bin/bash\necho "$*" >> "$SSH_TRACE"\n[[ "$1" == -G ]] || exit 99\necho "hostname 39.106.39.110"\n')
            ssh.chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/deploy_sparkservice.sh")],
                env={**os.environ, "PATH": f"{folder}:{os.environ['PATH']}", "SSH_TRACE": str(trace),
                     "SRC_DIR": str(ROOT), "DEPLOY_ENV_FILE": str(envfile), "PYTHON_BIN": sys.executable,
                     "BUILD_FRONTEND_LOCAL": "0", "USE_RSYNC": "0", "SYNC_DEPLOY_ENV": "1"},
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DB_HOST", result.stderr)
            self.assertNotIn("must-not-appear", result.stdout + result.stderr)
            self.assertEqual(trace.read_text().splitlines(), ["-G root@39.106.39.110"])


class RemoteReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.base = self.folder / "production"
        self.stage = self.base / "uploads/20261021_120000_123_456"
        self.stage.mkdir(parents=True)
        shutil.copytree(TEMPLATE, self.stage / "server")
        self.active_env = self.base / ".deploy.env"
        self.active_env.write_text("DB_PASSWORD=old-password\n")
        self.stage.joinpath("candidate.env").write_text("DB_PASSWORD=new-password\n")
        self.stage.joinpath("release.txt").write_text("commit=test-commit\n")
        self.frontend = self.base / "shared/frontend-dist"
        self.frontend.mkdir(parents=True)
        self.frontend.joinpath("index.html").write_text("old-frontend")
        self.stage.joinpath("frontend").mkdir()
        self.stage.joinpath("frontend/index.html").write_text("new-frontend")
        self.base.joinpath("docker-compose.yml").write_text("old-compose")
        self.base.joinpath("docker").mkdir()
        self.base.joinpath("docker/old-marker").write_text("keep")
        self.base.joinpath("bin").mkdir()
        self.old_release = self.base / "releases/old"
        self.old_release.mkdir(parents=True)
        self.base.joinpath("current").symlink_to(self.old_release)
        archive = self.stage / "sparkservice.tgz"
        with tarfile.open(archive, "w:gz") as package:
            contents = b"print('test package')\n"
            member = tarfile.TarInfo("manage.py")
            member.size = len(contents)
            package.addfile(member, io.BytesIO(contents))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.stage.joinpath("sparkservice.tgz.sha256").write_text(f"{digest}  sparkservice.tgz\n")
        self.fakebin = self.folder / "fakebin"
        self.fakebin.mkdir()
        self.trace = self.folder / "docker-trace"
        self.env = {
            **os.environ, "PATH": f"{self.fakebin}:{os.environ['PATH']}",
            "SPARK_BASE": str(self.base), "RELEASE_TARGET_IP": "39.106.39.110",
            "FAKE_TRACE": str(self.trace), "RESET_DATABASE_NAME": "",
        }
        self.executable("flock", '#!/bin/bash\nexit "${LOCK_BUSY:-0}"\n')
        self.executable("timeout", '#!/bin/bash\nshift\nexec "$@"\n')
        self.executable("sleep", "#!/bin/bash\nexit 0\n")
        self.executable("curl", "#!/bin/bash\nexit 0\n")
        self.executable("df", "#!/bin/bash\necho 'Filesystem 1024-blocks Used Available Capacity Mounted'\necho 'test 4000000 1000000 3000000 25% /'\n")
        self.executable("mysqldump", '#!/bin/bash\n[[ "${BACKUP_FAIL:-0}" == 0 ]] || exit 21\necho "CREATE TABLE test (id INT);"\n')
        self.executable("sha256sum", f"#!{sys.executable}\n" + '''import hashlib
from pathlib import Path
import sys
expected, filename = Path(sys.argv[2]).read_text().split()
sys.exit(0 if hashlib.sha256(Path(filename).read_bytes()).hexdigest() == expected else 1)
''')
        self.executable("docker", f"#!{sys.executable}\n" + '''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["FAKE_TRACE"]).open("a") as stream:
    stream.write(json.dumps({"args": args, "env": Path(os.environ["SPARK_BASE"], ".deploy.env").read_text()}) + "\\n")
if args[0] == "inspect":
    health = "unhealthy" if os.environ.get("BAD_HEALTH") == args[-1] else "healthy"
    print(json.dumps([{"State": {"Running": True, "Health": {"Status": health}}}]))
    sys.exit(0)
failure = os.environ.get("DOCKER_FAIL", "")
if failure and failure in " ".join(args):
    sys.exit(42)
if "ps" in args and "-q" in args:
    service = next((arg.split("=", 2)[-1] for arg in args if arg.startswith("label=com.docker.compose.service=")), args[-1])
    print(service)
''')

    def executable(self, name, text):
        path = self.fakebin / name
        path.write_text(text)
        path.chmod(0o755)

    def run_release(self, **overrides):
        return subprocess.run(
            ["bash", str(self.stage / "server/bin/deploy_remote.sh"), str(self.stage / "sparkservice.tgz")],
            env={**self.env, **overrides}, capture_output=True, text=True, timeout=40,
        )

    def assert_old_release_untouched(self):
        self.assertEqual(self.active_env.read_text(), "DB_PASSWORD=old-password\n")
        self.assertEqual(self.frontend.joinpath("index.html").read_text(), "old-frontend")
        self.assertEqual(self.base.joinpath("current").resolve(), self.old_release)
        self.assertEqual(self.base.joinpath("docker-compose.yml").read_text(), "old-compose")

    def test_database_authentication_failure_preserves_production(self):
        result = self.run_release(DOCKER_FAIL="release_checks.py connections")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("check-connections", result.stderr)
        self.assert_old_release_untouched()
        trace = self.trace.read_text()
        self.assertNotIn("--noinput", trace)
        self.assertNotIn('"up"', trace)
        self.assertNotIn("new-password", trace)

    def test_lock_conflict_and_corrupt_package_never_touch_production(self):
        result = self.run_release(LOCK_BUSY="1")
        self.assertEqual(result.returncode, 75)
        self.assertFalse(self.trace.exists())
        self.assert_old_release_untouched()
        self.stage.joinpath("sparkservice.tgz").write_bytes(b"corrupt")
        result = self.run_release()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.trace.exists())
        self.assert_old_release_untouched()

    def test_backup_and_migration_failures_do_not_promote(self):
        result = self.run_release(BACKUP_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backup-database", result.stderr)
        self.assert_old_release_untouched()

    def test_migration_failure_retains_database_backup(self):
        result = self.run_release(DOCKER_FAIL="migrate --noinput")
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_release_untouched()
        self.assertTrue(list(self.base.joinpath("shared/backups").glob("*.sql.gz")))

    def test_success_promotes_only_after_checks_and_keeps_previous_files(self):
        result = self.run_release()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Release complete:", result.stdout)
        self.assertIn("DB_PASSWORD=new-password", self.active_env.read_text())
        self.assertIn("SPARK_BACKEND_IMAGE=localhost/traveldiary-backend:20261021_120000_123_456", self.active_env.read_text())
        self.assertEqual(self.frontend.joinpath("index.html").read_text(), "new-frontend")
        self.assertEqual(self.base.joinpath("current").resolve(), self.base / "releases" / self.stage.name)
        self.assertEqual(self.stage.joinpath("previous.env").read_text(), "DB_PASSWORD=old-password\n")
        self.assertEqual(self.stage.joinpath("previous-frontend/index.html").read_text(), "old-frontend")
        records = [json.loads(line) for line in self.trace.read_text().splitlines()]
        for record in records:
            if "connections" in record["args"] or "--noinput" in record["args"]:
                self.assertEqual(record["env"], "DB_PASSWORD=old-password\n")
        self.assertIn("phase=complete", self.stage.joinpath("result.txt").read_text())

    def test_worker_failure_does_not_report_success_or_advance_current(self):
        result = self.run_release(DOCKER_FAIL="release_checks.py workers")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Release complete:", result.stdout)
        self.assertEqual(self.base.joinpath("current").resolve(), self.old_release)
        self.assertIn("activating=1", self.stage.joinpath("result.txt").read_text())
        self.assertTrue(self.stage.joinpath("previous.env").exists())

    def test_unhealthy_frontend_is_not_success(self):
        result = self.run_release(BAD_HEALTH="frontend")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Release complete:", result.stdout)
        self.assertEqual(self.base.joinpath("current").resolve(), self.old_release)

    def run_entry_release(self, use_rsync):
        source = self.folder / "source"
        source.mkdir()
        source.joinpath("manage.py").write_text("print('test source')\n")
        source.joinpath("requirements.txt").write_text("Django\n")
        source.joinpath(".env").write_text("".join(f"{key}='{value}'\n" for key, value in production_config().items()))
        frontend = source / "backoffice-web"
        frontend.joinpath("dist").mkdir(parents=True)
        frontend.joinpath("package.json").write_text("{}")
        frontend.joinpath("pnpm-lock.yaml").write_text("lockfileVersion: '9.0'")
        frontend.joinpath("dist/index.html").write_text("entry-frontend")
        self.executable("pnpm", "#!/bin/bash\nexit 0\n")
        self.executable("git", '''#!/bin/bash
case "$*" in
  *symbolic-ref*|*branch*) echo TravelDiary ;;
  *rev-parse*) echo test-commit ;;
esac
''')
        self.executable("ssh", '''#!/bin/bash
if [[ "$1" == -G ]]; then echo 'hostname 39.106.39.110'; exit 0; fi
while [[ "$1" == -o ]]; do shift 2; done
shift
exec bash -c "$1"
''')
        self.executable("scp", f"#!{sys.executable}\n" + '''import shutil, sys
from pathlib import Path
args = sys.argv[1:]
while args[0] == "-o":
    args = args[2:]
destination = Path(args[-1].split(":", 1)[1])
for source in args[:-1]:
    shutil.copy(source, destination)
''')
        self.executable("rsync", f"#!{sys.executable}\n" + '''import shutil, sys
source, destination = sys.argv[-2:]
shutil.copytree(source, destination.split(":", 1)[1], dirs_exist_ok=True)
''')
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/deploy_sparkservice.sh")],
            env={**self.env, "SRC_DIR": str(source), "SERVER_TEMPLATE_DIR": str(TEMPLATE), "REMOTE_BASE": str(self.base),
                 "REMOTE_HOST": "root@39.106.39.110", "DEPLOY_ENV_FILE": str(source / ".env"),
                 "FRONTEND_DIR": str(frontend), "PYTHON_BIN": sys.executable, "SYNC_DEPLOY_ENV": "1",
                 "USE_RSYNC": str(use_rsync), "BUILD_FRONTEND_LOCAL": "1", "CANCEL_RUNNING_DEPLOY": "0"},
            capture_output=True, text=True, timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SparkService deployed:", result.stdout)
        current = self.base.joinpath("current").resolve()
        self.assertEqual(current.joinpath("manage.py").read_text(), "print('test source')\n")
        self.assertFalse(current.joinpath(".env").exists())
        self.assertEqual(self.frontend.joinpath("index.html").read_text(), "entry-frontend")
        self.assertIn("DB_PASSWORD='test-password'", self.active_env.read_text())

    def test_entry_to_remote_release_with_rsync_upload(self):
        self.run_entry_release(use_rsync=1)

    def test_entry_to_remote_release_with_scp_fallback(self):
        self.run_entry_release(use_rsync=0)


if __name__ == "__main__":
    unittest.main()
