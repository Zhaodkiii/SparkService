import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import LoginAudit
from backoffice.models import AdminRole, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions
from backoffice.system_logs.parsers import match_status, parse_log_line
from backoffice.system_logs.registry import resolve_log_file
from backoffice.system_logs.service import SystemLogQuery, SystemLogService


User = get_user_model()


class SystemLogParserTests(TestCase):
    def test_parse_console_access_line(self):
        line = (
            "INFO 2026-07-30 14:04:27,848 accounts.request "
            "[request_id=abc-123] HTTP 请求摘要: POST /api/v1/auth/apple/login/ status=401 duration_ms=1365 bytes=116"
        )
        row = parse_log_line(line)
        self.assertEqual(row["parse_status"], "parsed")
        self.assertEqual(row["status_code"], 401)
        self.assertEqual(row["duration_ms"], 1365)
        self.assertEqual(row["path"], "/api/v1/auth/apple/login/")

    def test_parse_json_line(self):
        line = (
            '{"ts":"2026-07-30T14:04:27.859+08:00","level":"WARNING","logger":"accounts.api_io",'
            '"request_id":"abc","path":"/api/v1/auth/apple/login/","status_code":401,"message":"HTTP 响应摘要"}'
        )
        row = parse_log_line(line)
        self.assertEqual(row["parse_status"], "parsed")
        self.assertEqual(row["status_code"], 401)

    def test_match_status_4xx(self):
        self.assertTrue(match_status({"status_code": 401}, "4xx"))
        self.assertFalse(match_status({"status_code": 200}, "4xx"))


class SystemLogServiceTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_root = Path(self.temp_dir.name)
        self.date = "2026-07-30"
        day_dir = self.log_root / self.date
        day_dir.mkdir(parents=True)
        (day_dir / "access.log").write_text(
            "INFO 2026-07-30 14:04:27,848 accounts.request [request_id=req-1] HTTP 请求摘要: POST /api/v1/auth/apple/login/ status=401 duration_ms=100 bytes=10\n"
            "INFO 2026-07-30 14:05:27,848 accounts.request [request_id=req-2] HTTP 请求摘要: GET /api/v1/auth/session/ status=200 duration_ms=20 bytes=10\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_modules_includes_log_root(self):
        with override_settings(LOG_ROOT=str(self.log_root), LOG_HOST_PATH_HINT="/root/2026/shared/logs"):
            payload = SystemLogService.list_modules()
        self.assertEqual(payload["log_root"], str(self.log_root.resolve()))
        self.assertEqual(payload["date_pattern"], "YYYY-MM-DD")
        self.assertEqual(payload["host_path_hint"], "/root/2026/shared/logs")
        self.assertTrue(any(item["value"] == "access" for item in payload["items"]))

    @override_settings(LOG_ROOT=tempfile.gettempdir())
    def test_query_filters_status_and_request_id(self):
        with override_settings(LOG_ROOT=str(self.log_root)):
            payload = SystemLogService.query(
                SystemLogQuery(date=self.date, module="access", status="401", request_id="req-1")
            )
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["items"][0]["status_code"], 401)
        self.assertEqual(payload["context"]["log_root"], str(self.log_root.resolve()))
        self.assertEqual(payload["context"]["file"], "access.log")
        self.assertTrue(payload["context"]["file_exists"])

    @override_settings(LOG_ROOT="/tmp")
    def test_resolve_log_file_rejects_invalid_module(self):
        with self.assertRaises(Exception):
            resolve_log_file(date="2026-07-30", module="invalid_module")


class AdminSystemLogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_root = Path(self.temp_dir.name)
        self.date = "2026-07-30"
        day_dir = self.log_root / self.date
        day_dir.mkdir(parents=True)
        (day_dir / "access.log").write_text(
            "INFO 2026-07-30 14:04:27,848 accounts.request [request_id=req-1] HTTP 请求摘要: POST /api/v1/auth/apple/login/ status=401 duration_ms=100 bytes=10\n",
            encoding="utf-8",
        )

        self.staff_user = User.objects.create_user(
            username="audit_staff",
            email="audit@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="audit_normal",
            email="normal@example.com",
            password="pass1234",
            is_staff=False,
        )
        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_system_logs_require_staff(self):
        self.client.force_authenticate(user=self.normal_user)
        with override_settings(LOG_ROOT=str(self.log_root)):
            response = self.client.get(
                "/api/admin/v1/audit/system-logs/",
                {"date": self.date, "module": "access"},
            )
        self.assertEqual(response.status_code, 403)

    def test_system_logs_list(self):
        self.client.force_authenticate(user=self.staff_user)
        with override_settings(LOG_ROOT=str(self.log_root), LOG_HOST_PATH_HINT="/root/2026/shared/logs"):
            response = self.client.get(
                "/api/admin/v1/audit/system-logs/",
                {"date": self.date, "module": "access", "status": "401"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(data["items"][0]["status_code"], 401)
        self.assertEqual(data["context"]["log_root"], str(self.log_root.resolve()))
        self.assertIn("access.log", data["context"]["log_file"])

    def test_system_log_modules_includes_path_metadata(self):
        self.client.force_authenticate(user=self.staff_user)
        with override_settings(LOG_ROOT=str(self.log_root), LOG_HOST_PATH_HINT="/root/2026/shared/logs"):
            response = self.client.get("/api/admin/v1/audit/system-log-modules/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["log_root"], str(self.log_root.resolve()))
        self.assertEqual(data["host_path_hint"], "/root/2026/shared/logs")
        self.assertTrue(any(item["value"] == "access" for item in data["items"]))


class AdminLoginAuditApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="login_audit_staff",
            email="login-audit@example.com",
            password="pass1234",
            is_staff=True,
        )
        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)
        LoginAudit.objects.create(
            provider=LoginAudit.LoginProvider.APPLE,
            outcome=LoginAudit.LoginOutcome.FAILED,
            bundle_id="cn.zhaodk.SupportClient",
            device_id="device-1",
            request_id="req-apple-fail",
            raw_claims={
                "status_code": 401,
                "error_code": 40162,
                "error_message": "device_credential_not_registered",
            },
        )

    def test_login_audit_filter_by_outcome(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/audit/login-logs/", {"outcome": "failed"})
        self.assertEqual(response.status_code, 200)
        items = response.json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["raw_claims"]["error_code"], 40162)
