import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, Max, Prefetch, F, Case, When, IntegerField, Value, DateTimeField, TextField, Exists, OuterRef
from django.db.models.functions import Coalesce, Greatest, Cast
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.serializers import BooleanField, CharField, Serializer
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.models import (
    AccountDeactivation,
    AccountDeactivationAudit,
    AccountDeviceSession,
    LoginAudit,
    SocialIdentity,
    TrustedDevice,
)
from accounts.deactivation.tasks import process_deactivation_task
from accounts.services.phone_number_service import PhoneNumberService
from ai_config.models import (
    AIModelCatalog,
    AIProviderKeyConfig,
    AIScenarioModelBinding,
    ScenarioKey,
    SmallTask,
    SparkToolName,
    TrialApplication,
    TrialApplicationRequest,
)
from ai_config.services import TrialService
from app_version.models import AppVersionConfig, VersionCheckLog
from chat_sync.models import ChatMessage, ChatThread
from common.permissions import AdminCodePermission, AdminOnlyPermission
from common.response import error_response, success_response
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult
from file_manager.models import ManagedFile
from medical.models import MedicalCase, Member

from backoffice.audit import write_audit_log
from backoffice.models import AdminAuditLog, AdminPermission, AdminRole, AdminRolePermission, AdminUserRole
from backoffice.query_params import InvalidAdminDatetimeParam, parse_admin_datetime_param
from backoffice.rbac import bootstrap_admin_permissions, get_user_menu_tree, get_user_permission_codes, get_user_role_codes
from backoffice.sorting import resolve_admin_sort
from backoffice.serializers import (
    AdminAIModelCatalogCreateSerializer,
    AdminAIModelCatalogSerializer,
    AdminAIModelCatalogUpdateSerializer,
    AdminAIProviderKeyCreateSerializer,
    AdminAIProviderKeySerializer,
    AdminAIProviderKeyUpdateSerializer,
    AdminAIScenarioModelBindingSerializer,
    AdminSmallTaskSerializer,
    AdminAuditLogSerializer,
    AdminDeactivationAuditSerializer,
    AdminDeactivationSerializer,
    AdminDeviceRevokeSerializer,
    AdminDeviceSerializer,
    AdminNotificationCampaignSerializer,
    AdminNotificationLogQuerySerializer,
    AdminNotificationMessageSerializer,
    AdminNotificationSendSerializer,
    AdminNotificationTemplatePreviewSerializer,
    AdminNotificationTemplateSerializer,
    AdminNotificationUserQuerySerializer,
    AdminPermissionSerializer,
    AdminRolePermissionAssignSerializer,
    AdminRoleSerializer,
    AdminTrialActionSerializer,
    AdminTrialApplicationSerializer,
    AdminUserDeviceSessionSerializer,
    AdminUserListSerializer,
    AdminUserProGrantSerializer,
    AdminUserProRecycleSerializer,
    AdminUserRoleAssignSerializer,
    AdminUserSerializer,
    AdminUserSocialIdentitySerializer,
    AdminUserStatusSerializer,
    AdminUserTrustedDeviceSerializer,
    AppVersionConfigSerializer,
    VersionCheckLogSerializer,
)
from notification_center.models import NotificationCampaign, NotificationMessage, NotificationTemplate
from notification_center.services import NotificationCenterService


User = get_user_model()
BASE_DIR = Path(__file__).resolve().parent.parent
RUN_DIR = BASE_DIR / "run"
LOG_DIR = BASE_DIR / "logs"
ADMIN_LOGIN_TOKEN_LIFETIME_DEFAULT = timedelta(days=1)
ADMIN_LOGIN_TOKEN_LIFETIME_REMEMBER = timedelta(days=30)
ADMIN_TOKEN_LIFETIME_CLAIM = "admin_token_lifetime_seconds"
# MySQL GREATEST 遇 NULL 即返回 NULL；排序前 Coalesce 到哨兵值，并 Cast 为 char 避免驱动转换异常
_LAST_USED_SORT_EPOCH = Cast(Value("1970-01-01 00:00:00"), DateTimeField())


def _last_used_greatest_expr():
    return Greatest(
        Coalesce(F("_max_device_seen"), _LAST_USED_SORT_EPOCH),
        Coalesce(F("_max_session_refresh"), _LAST_USED_SORT_EPOCH),
        Coalesce(F("last_login"), _LAST_USED_SORT_EPOCH),
    )


def _has_last_used_case():
    return Case(
        When(
            Q(_max_device_seen__isnull=False)
            | Q(_max_session_refresh__isnull=False)
            | Q(last_login__isnull=False),
            then=Value(1),
        ),
        default=Value(0),
        output_field=IntegerField(),
    )


def _annotate_users_last_used(queryset, *, include_sort_text: bool = False):
    greatest = _last_used_greatest_expr()
    annotations = {
        "has_last_used": _has_last_used_case(),
        "last_used_sort_dt": greatest,
    }
    if include_sort_text:
        annotations["last_used_sort"] = Cast(greatest, TextField())
    return queryset.annotate(**annotations)


def _build_admin_user_search_filter(query: str) -> Q:
    q = (query or "").strip()
    if not q:
        return Q()
    filters = Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q)
    if q.isdigit():
        filters |= Q(id=int(q))
    phone_candidates: set[str] = {q}
    if q.isdigit() and len(q) >= 7:
        try:
            phone_candidates.add(PhoneNumberService.normalize_e164(q))
        except Exception:
            pass
        if not q.startswith("+"):
            try:
                phone_candidates.add(PhoneNumberService.normalize_e164(f"+{q}"))
            except Exception:
                pass
    elif q.startswith(("+", "00")):
        try:
            phone_candidates.add(PhoneNumberService.normalize_e164(q))
        except Exception:
            pass
    phone_user_ids = SocialIdentity.objects.filter(
        provider=SocialIdentity.Provider.PHONE,
        provider_uid__in=[value for value in phone_candidates if value],
    ).values_list("user_id", flat=True)
    if phone_user_ids:
        filters |= Q(id__in=phone_user_ids)
    return filters


class AdminAccessToken(AccessToken):
    lifetime = ADMIN_LOGIN_TOKEN_LIFETIME_DEFAULT

    def set_exp(
        self,
        claim: str = "exp",
        from_time=None,
        lifetime=None,
    ) -> None:
        if lifetime is None and ADMIN_TOKEN_LIFETIME_CLAIM in self.payload:
            lifetime = timedelta(seconds=int(self.payload[ADMIN_TOKEN_LIFETIME_CLAIM]))
        super().set_exp(claim=claim, from_time=from_time, lifetime=lifetime)


class AdminRefreshToken(RefreshToken):
    lifetime = ADMIN_LOGIN_TOKEN_LIFETIME_DEFAULT
    access_token_class = AdminAccessToken

    def set_exp(
        self,
        claim: str = "exp",
        from_time=None,
        lifetime=None,
    ) -> None:
        if lifetime is None and ADMIN_TOKEN_LIFETIME_CLAIM in self.payload:
            lifetime = timedelta(seconds=int(self.payload[ADMIN_TOKEN_LIFETIME_CLAIM]))
        super().set_exp(claim=claim, from_time=from_time, lifetime=lifetime)

    @property
    def access_token(self) -> AdminAccessToken:
        access = self.access_token_class()
        no_copy = self.no_copy_claims
        for claim, value in self.payload.items():
            if claim in no_copy:
                continue
            access[claim] = value
        access.set_exp(from_time=self.current_time)
        return access


def issue_admin_login_tokens(user, *, remember_me: bool = False) -> AdminRefreshToken:
    lifetime = ADMIN_LOGIN_TOKEN_LIFETIME_REMEMBER if remember_me else ADMIN_LOGIN_TOKEN_LIFETIME_DEFAULT
    refresh = AdminRefreshToken.for_user(user)
    refresh[ADMIN_TOKEN_LIFETIME_CLAIM] = int(lifetime.total_seconds())
    refresh.set_exp(from_time=refresh.current_time, lifetime=lifetime)
    return refresh


def _read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        content = pid_file.read_text(encoding="utf-8").strip()
        if not content:
            return None
        return int(content)
    except (ValueError, OSError):
        return None


def _is_pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _ensure_run_dirs() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _start_process_if_needed(pid_filename: str, name: str, command: list[str]) -> dict:
    _ensure_run_dirs()
    pid_file = RUN_DIR / pid_filename
    pid = _read_pid(pid_file)
    if _is_pid_running(pid):
        return {"name": name, "action": "already_running", "pid": pid}

    if pid_file.exists() and not _is_pid_running(pid):
        pid_file.unlink(missing_ok=True)

    stdout_path = LOG_DIR / f"{name}.stdout.log"
    stderr_path = LOG_DIR / f"{name}.stderr.log"
    with stdout_path.open("ab") as out_f, stderr_path.open("ab") as err_f:
        proc = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=out_f,
            stderr=err_f,
            start_new_session=True,
        )

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    return {"name": name, "action": "started", "pid": proc.pid}


def _stop_process(pid_filename: str, name: str) -> dict:
    pid_file = RUN_DIR / pid_filename
    pid = _read_pid(pid_file)
    if not pid:
        pid_file.unlink(missing_ok=True)
        return {"name": name, "action": "not_running"}

    if not _is_pid_running(pid):
        pid_file.unlink(missing_ok=True)
        return {"name": name, "action": "stale_pid_cleaned", "pid": pid}

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pid_file.unlink(missing_ok=True)
        return {"name": name, "action": "not_running", "pid": pid}

    stopped = False
    for _ in range(20):
        if not _is_pid_running(pid):
            stopped = True
            break
        time.sleep(0.2)

    if not stopped:
        try:
            os.kill(pid, signal.SIGKILL)
            stopped = True
        except OSError:
            stopped = not _is_pid_running(pid)

    pid_file.unlink(missing_ok=True)
    return {"name": name, "action": "stopped" if stopped else "stop_requested", "pid": pid}


def _celery_ping_status() -> dict:
    timeout_seconds = 4
    cmd = [sys.executable, "-m", "celery", "-A", "SparkService", "inspect", "ping", "--timeout=2"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = (proc.stdout or "").strip()
        healthy = proc.returncode == 0 and "pong" in output.lower()
        return {
            "healthy": healthy,
            "returncode": proc.returncode,
            "output": output[:500],
            "error": (proc.stderr or "").strip()[:500],
        }
    except Exception as exc:
        return {"healthy": False, "returncode": -1, "output": "", "error": str(exc)[:500]}


def _celery_worker_queue_names() -> list[str]:
    configured = (os.getenv("CELERY_QUEUES") or getattr(settings, "CELERY_QUEUES", "") or "").strip()
    names = [item.strip() for item in configured.split(",") if item.strip()]
    if not names:
        names = ["celery"]
    for route in (getattr(settings, "CELERY_TASK_ROUTES", {}) or {}).values():
        if isinstance(route, dict):
            queue = str(route.get("queue") or "").strip()
            if queue:
                names.append(queue)
    return list(dict.fromkeys(names))


def _redis_broker_display(broker_url: str) -> str:
    try:
        parsed = urlparse(broker_url)
        if (parsed.scheme or "").lower() == "unix":
            path = parsed.path or ""
            return path[:120] if path else "unix"
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port if parsed.port is not None else 6379
        db = (parsed.path or "/0").strip("/") or "0"
        return f"{host}:{port}/{db}"
    except Exception:
        return "(unparsed)"


def _celery_redis_status() -> dict:
    raw = (getattr(settings, "CELERY_BROKER_URL", None) or "").strip()
    if not raw:
        return {"healthy": False, "display": "-", "error": "CELERY_BROKER_URL not configured"}

    scheme = (urlparse(raw).scheme or "").lower()
    if "redis" not in scheme and scheme != "unix":
        return {
            "healthy": False,
            "display": _redis_broker_display(raw),
            "error": f"broker scheme is not redis: {scheme or '(empty)'}",
        }

    try:
        import redis as redis_lib

        client = redis_lib.from_url(raw, socket_connect_timeout=2.0, socket_timeout=2.0)
        client.ping()
        return {"healthy": True, "display": _redis_broker_display(raw), "error": ""}
    except Exception as exc:
        return {"healthy": False, "display": _redis_broker_display(raw), "error": str(exc)[:500]}


def _redis_start_command_from_settings() -> str:
    return (os.getenv("REDIS_START_COMMAND") or getattr(settings, "REDIS_START_COMMAND", "") or "").strip()


def _redis_stop_command_from_settings() -> str:
    return (os.getenv("REDIS_STOP_COMMAND") or getattr(settings, "REDIS_STOP_COMMAND", "") or "").strip()


def _redis_locally_manageable(broker_url: str) -> bool:
    broker_url = (broker_url or "").strip()
    if not broker_url:
        return False
    if _redis_start_command_from_settings() or _redis_stop_command_from_settings():
        return True
    parsed = urlparse(broker_url)
    scheme = (parsed.scheme or "").lower()
    if "redis" not in scheme:
        return False
    if scheme == "unix":
        return False
    if "+" in scheme:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return True
    return host in ("127.0.0.1", "localhost", "::1")


def _redis_broker_tcp_port(broker_url: str) -> int:
    try:
        parsed = urlparse(broker_url)
        if parsed.port is not None:
            return int(parsed.port)
    except (TypeError, ValueError):
        pass
    return 6379


def _run_subprocess_logged(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out[:800], (proc.stderr or "").strip()[:400]


def _try_start_local_redis() -> dict:
    raw = (getattr(settings, "CELERY_BROKER_URL", None) or "").strip()
    if not raw:
        return {"name": "redis", "action": "skipped_no_broker_url"}

    if not _redis_locally_manageable(raw):
        return {"name": "redis", "action": "skipped_remote_or_unix_broker_set_redis_start_command"}

    if _celery_redis_status()["healthy"]:
        return {"name": "redis", "action": "already_running"}

    custom = _redis_start_command_from_settings()
    if custom:
        try:
            cmd = shlex.split(custom, posix=(os.name != "nt"))
        except ValueError as exc:
            return {"name": "redis", "action": f"invalid_redis_start_command:{exc}"[:200]}
        rc, combined, _err = _run_subprocess_logged(cmd, timeout=45)
        time.sleep(0.4)
        if _celery_redis_status()["healthy"]:
            return {"name": "redis", "action": "started_custom_command", "pid": None}
        return {"name": "redis", "action": f"custom_command_failed_rc{rc}:{combined}"[:500]}

    port = _redis_broker_tcp_port(raw)
    redis_bin = shutil.which("redis-server")
    if redis_bin:
        cmd = [redis_bin, "--port", str(port), "--daemonize", "yes"]
        rc, combined, _err = _run_subprocess_logged(cmd, timeout=15)
        time.sleep(0.4)
        if _celery_redis_status()["healthy"]:
            return {"name": "redis", "action": "started_redis_server", "pid": None}

    brew_hint = ""
    if sys.platform == "darwin":
        rc, combined, _err = _run_subprocess_logged(["brew", "services", "start", "redis"], timeout=30)
        time.sleep(1.0)
        if _celery_redis_status()["healthy"]:
            return {"name": "redis", "action": "started_brew_services", "pid": None}
        brew_hint = combined if (rc != 0 and combined) else f"rc={rc}"

    if sys.platform == "linux":
        for unit in ("redis-server", "redis"):
            rc, combined, _err = _run_subprocess_logged(["systemctl", "start", unit], timeout=30)
            time.sleep(0.6)
            if _celery_redis_status()["healthy"]:
                return {"name": "redis", "action": f"started_systemctl_{unit}", "pid": None}

    last = "no_strategy_succeeded"
    if sys.platform == "darwin" and brew_hint:
        last = f"brew:{brew_hint[:400]}"
    return {"name": "redis", "action": f"start_failed:{last}"[:500]}


def _try_stop_local_redis() -> dict:
    raw = (getattr(settings, "CELERY_BROKER_URL", None) or "").strip()
    if not raw:
        return {"name": "redis", "action": "skipped_no_broker_url"}

    if not _redis_locally_manageable(raw):
        return {"name": "redis", "action": "skipped_remote_or_unix_broker_set_redis_stop_command"}

    if not _celery_redis_status()["healthy"]:
        return {"name": "redis", "action": "already_stopped"}

    custom = _redis_stop_command_from_settings()
    if custom:
        try:
            cmd = shlex.split(custom, posix=(os.name != "nt"))
        except ValueError as exc:
            return {"name": "redis", "action": f"invalid_redis_stop_command:{exc}"[:200]}
        rc, combined, _err = _run_subprocess_logged(cmd, timeout=45)
        time.sleep(0.5)
        if not _celery_redis_status()["healthy"]:
            return {"name": "redis", "action": "stopped_custom_command", "pid": None}
        return {"name": "redis", "action": f"custom_stop_failed_rc{rc}:{combined}"[:500]}

    port = _redis_broker_tcp_port(raw)
    cli = shutil.which("redis-cli")
    if cli:
        _run_subprocess_logged([cli, "-p", str(port), "shutdown"], timeout=15)
        time.sleep(0.5)
        if not _celery_redis_status()["healthy"]:
            return {"name": "redis", "action": "stopped_redis_cli", "pid": None}

    if sys.platform == "darwin":
        _run_subprocess_logged(["brew", "services", "stop", "redis"], timeout=30)
        time.sleep(0.8)
        if not _celery_redis_status()["healthy"]:
            return {"name": "redis", "action": "stopped_brew_services", "pid": None}

    if sys.platform == "linux":
        for unit in ("redis-server", "redis"):
            _run_subprocess_logged(["systemctl", "stop", unit], timeout=30)
            time.sleep(0.6)
            if not _celery_redis_status()["healthy"]:
                return {"name": "redis", "action": f"stopped_systemctl_{unit}", "pid": None}

    if not _celery_redis_status()["healthy"]:
        return {"name": "redis", "action": "stopped", "pid": None}

    return {"name": "redis", "action": "stop_failed:still_reachable", "pid": None}


def _get_celery_runtime_status() -> dict:
    worker_pid = _read_pid(RUN_DIR / "celery_worker.pid")
    beat_pid = _read_pid(RUN_DIR / "celery_beat.pid")
    worker_running = _is_pid_running(worker_pid)
    beat_running = _is_pid_running(beat_pid)
    ping = _celery_ping_status() if worker_running else {"healthy": False, "returncode": -1, "output": "", "error": "worker_not_running"}
    redis_status = _celery_redis_status()
    broker_url = (getattr(settings, "CELERY_BROKER_URL", None) or "").strip()
    redis_status["local_manageable"] = _redis_locally_manageable(broker_url)

    return {
        "host": socket.gethostname(),
        "worker": {"pid": worker_pid, "running": worker_running},
        "beat": {"pid": beat_pid, "running": beat_running},
        "overall_running": worker_running and beat_running,
        "ping": ping,
        "redis": redis_status,
        "worker_queues": _celery_worker_queue_names(),
        "chat_ai": {
            "server_runs_enabled": bool(getattr(settings, "CHAT_AI_SERVER_RUNS_ENABLED", False)),
            "run_executor": str(getattr(settings, "CHAT_AI_RUN_EXECUTOR", "disabled")),
        },
        "run_dir": str(RUN_DIR),
        "log_dir": str(LOG_DIR),
    }


class AdminLoginSerializer(Serializer):
    username = CharField(max_length=150)
    password = CharField(max_length=128)
    remember_me = BooleanField(required=False, default=False)


class AdminAuthLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]
        remember_me = serializer.validated_data.get("remember_me", False)

        user = authenticate(request=request, username=username, password=password)
        if user is None or not user.is_active:
            write_audit_log(request, action="admin.login.failed", resource_type="auth", status_code=401)
            return error_response(msg="invalid_credentials", code=40101, status_code=status.HTTP_401_UNAUTHORIZED)

        if not (user.is_staff or user.is_superuser):
            write_audit_log(request, action="admin.login.denied", resource_type="auth", status_code=403)
            return error_response(msg="not_admin_user", code=40301, status_code=status.HTTP_403_FORBIDDEN)

        token = issue_admin_login_tokens(user, remember_me=remember_me)
        payload = {
            "access": str(token.access_token),
            "refresh": str(token),
            "user": AdminUserSerializer(user).data,
        }
        write_audit_log(request, action="admin.login.success", resource_type="auth", resource_id=str(user.id), status_code=200)
        return success_response(payload, msg="login_success", code=0, status_code=status.HTTP_200_OK)


class AdminAuthProfileView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        bootstrap_admin_permissions()
        role_codes = get_user_role_codes(request.user.id)
        permission_codes = get_user_permission_codes(request.user.id)
        payload = {
            "user": AdminUserSerializer(request.user).data,
            "roles": role_codes,
            "permissions": permission_codes,
            "menus": get_user_menu_tree(request.user.id),
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminDashboardOverviewView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = {
            "users": {
                "total": User.objects.count(),
                "active": User.objects.filter(is_active=True).count(),
                "staff": User.objects.filter(is_staff=True).count(),
            },
            "chat": {
                "threads": ChatThread.objects.filter(is_deleted=False).count(),
                "messages": ChatMessage.objects.filter(tombstone=False).count(),
            },
            "medical": {
                "members": Member.objects.filter(is_deleted=False).count(),
                "cases": MedicalCase.objects.filter(is_deleted=False).count(),
            },
            "files": {
                "managed": ManagedFile.objects.filter(is_deleted=False).count(),
                "public": ManagedFile.objects.filter(is_deleted=False, is_public=True).count(),
            },
            "deactivation": {
                "requested": AccountDeactivation.objects.filter(state=AccountDeactivation.DeactivationState.REQUESTED).count(),
                "failed": AccountDeactivation.objects.filter(state=AccountDeactivation.DeactivationState.FAILED).count(),
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminUserListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        try:
            date_joined_after = parse_admin_datetime_param(request, "date_joined_after")
            date_joined_before = parse_admin_datetime_param(request, "date_joined_before")
            last_used_after = parse_admin_datetime_param(request, "last_used_after")
            last_used_before = parse_admin_datetime_param(request, "last_used_before")
        except InvalidAdminDatetimeParam as exc:
            return error_response(
                msg="invalid_datetime_param",
                code=40001,
                status_code=status.HTTP_400_BAD_REQUEST,
                data={"field": exc.field},
            )

        queryset = User.objects.select_related("trial_application").annotate(
            _max_device_seen=Max("trusted_devices__last_seen"),
            _max_session_refresh=Max("device_sessions__last_refreshed_at"),
        ).prefetch_related(
            Prefetch(
                "social_identities",
                queryset=SocialIdentity.objects.filter(provider=SocialIdentity.Provider.PHONE).order_by("-updated_at", "-id"),
                to_attr="_phone_identities",
            )
        )
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(_build_admin_user_search_filter(query))

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        bundle_id = (request.query_params.get("bundle_id") or "").strip()
        if bundle_id:
            device_exists = TrustedDevice.objects.filter(user_id=OuterRef("pk"), bundle_id=bundle_id)
            session_exists = AccountDeviceSession.objects.filter(user_id=OuterRef("pk"), bundle_id=bundle_id)
            audit_exists = LoginAudit.objects.filter(user_id=OuterRef("pk"), bundle_id=bundle_id)
            queryset = queryset.annotate(
                _bundle_device_exists=Exists(device_exists),
                _bundle_session_exists=Exists(session_exists),
                _bundle_audit_exists=Exists(audit_exists),
            ).filter(
                Q(_bundle_device_exists=True) | Q(_bundle_session_exists=True) | Q(_bundle_audit_exists=True)
            )

        if date_joined_after:
            queryset = queryset.filter(date_joined__gte=date_joined_after)
        if date_joined_before:
            queryset = queryset.filter(date_joined__lte=date_joined_before)

        sort_by = (request.query_params.get("sort_by") or "").strip()
        order = (request.query_params.get("order") or "").strip().lower()
        need_last_used_filter = last_used_after is not None or last_used_before is not None
        need_last_used_sort = sort_by == "last_used_at" and order in {"asc", "desc"}
        if need_last_used_filter or need_last_used_sort:
            queryset = _annotate_users_last_used(queryset, include_sort_text=need_last_used_sort)

        if last_used_after:
            queryset = queryset.filter(has_last_used=1, last_used_sort_dt__gte=last_used_after)
        if last_used_before:
            queryset = queryset.filter(has_last_used=1, last_used_sort_dt__lte=last_used_before)

        order_by = resolve_admin_sort(
            request,
            allowed={
                "id": {
                    "asc": ["id"],
                    "desc": ["-id"],
                },
                "date_joined": {
                    "asc": ["date_joined", "id"],
                    "desc": ["-date_joined", "-id"],
                },
                "last_used_at": {
                    # has_last_used 优先，保证升序/降序时空值都排在最后（兼容 MySQL）
                    "asc": ["-has_last_used", "last_used_sort", "id"],
                    "desc": ["-has_last_used", "-last_used_sort", "-id"],
                },
            },
            default=("date_joined", "desc"),
        )
        queryset = queryset.order_by(*order_by)

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        rows = AdminUserListSerializer(page_obj.object_list, many=True).data
        payload = {
            "items": rows,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminUserStatusView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:status:update"

    def post(self, request, user_id: int):
        target = get_object_or_404(User, pk=user_id)
        serializer = AdminUserStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if target.id == request.user.id and serializer.validated_data["is_active"] is False:
            return success_response(
                {"detail": "cannot_deactivate_self"},
                msg="invalid_operation",
                code=40001,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        target.is_active = serializer.validated_data["is_active"]
        target.save(update_fields=["is_active"])

        payload = AdminUserSerializer(target).data
        write_audit_log(
            request,
            action="admin.user.status.update",
            resource_type="user",
            resource_id=str(target.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminUserDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, user_id: int):
        user = get_object_or_404(User.objects.select_related("trial_application"), pk=user_id)
        trusted_devices = TrustedDevice.objects.filter(user=user).order_by("-last_seen", "-id")
        device_sessions = (
            AccountDeviceSession.objects.filter(user=user)
            .select_related("trusted_device")
            .order_by("-updated_at", "-id")
        )
        auth_identities = SocialIdentity.objects.filter(user=user).order_by("provider", "-updated_at", "-id")
        pro = TrialService.build_pro_summary(user=user)
        user_data = AdminUserSerializer(user).data
        user_data["is_pro"] = pro["is_pro"]
        user_data["pro_status"] = pro["status"]
        user_data["pro_expires_at"] = pro["expires_at"]
        payload = {
            "user": user_data,
            "pro": pro,
            "auth_identities": AdminUserSocialIdentitySerializer(auth_identities, many=True).data,
            "trusted_devices": AdminUserTrustedDeviceSerializer(trusted_devices, many=True).data,
            "device_sessions": AdminUserDeviceSessionSerializer(device_sessions, many=True).data,
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


def _send_membership_pro_notification(
    *,
    request,
    user_id: int,
    business_scene: str,
    title: str,
    body: str,
    business_id: str,
    channels: list[str],
    status_value: str,
    application_id=None,
):
    try:
        NotificationCenterService.send_to_user_sync(
            campaign_id=None,
            user_id=user_id,
            channels=channels,
            title=title,
            body=body,
            payload={
                "type": "ai_trial_application_result",
                "status": status_value,
                "application_id": application_id,
                "refresh_ai_config": True,
                "route": "ai_settings",
            },
            created_by_id=getattr(request.user, "id", None),
            request_id=getattr(request, "request_id", "") or "",
            business_scene=business_scene,
            business_reference_type="trial_application",
            business_id=business_id,
            idempotency_key=f"{business_scene}:{business_id}:manual",
            source="backoffice.user_pro",
            actor_type="admin",
            actor_id=str(getattr(request.user, "id", "") or ""),
        )
    except Exception:
        # 通知失败不影响 Pro 操作结果
        pass


class AdminUserProGrantView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:pro:grant"

    @transaction.atomic
    def post(self, request, user_id: int):
        target = get_object_or_404(User, pk=user_id)
        serializer = AdminUserProGrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "")
        try:
            trial, grant_req, previous_status = TrialService.admin_grant_user_trial(
                user=target,
                grant_days=serializer.validated_data.get("grant_days"),
                expires_at=serializer.validated_data.get("expires_at"),
                note=note,
            )
        except ValueError as exc:
            return error_response(msg=str(exc), code=40001, status_code=status.HTTP_400_BAD_REQUEST)

        _send_membership_pro_notification(
            request=request,
            user_id=target.id,
            business_scene="membership.pro_trial.manually_granted",
            title="已发放 Pro 试用权限",
            body="系统已为你发放 Pro 模型试用权限。",
            business_id=str(grant_req.id),
            channels=[
                NotificationMessage.Channel.APNS,
                NotificationMessage.Channel.EMAIL,
                NotificationMessage.Channel.SMS,
            ],
            status_value="active",
            application_id=grant_req.id,
        )

        pro = TrialService.build_pro_summary(user=target)
        payload = {"user_id": target.id, "pro": pro}
        write_audit_log(
            request,
            action="admin.user.pro.grant",
            resource_type="user",
            resource_id=str(target.id),
            status_code=200,
            response_payload={
                **payload,
                "trial_id": trial.id,
                "previous_status": previous_status,
                "new_status": trial.status,
                "expires_at": trial.expires_at.isoformat() if trial.expires_at else None,
                "note": note,
                "operator_user_id": getattr(request.user, "id", None),
            },
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminUserProRecycleView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:pro:recycle"

    @transaction.atomic
    def post(self, request, user_id: int):
        target = get_object_or_404(User, pk=user_id)
        serializer = AdminUserProRecycleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "")
        try:
            trial, previous_status = TrialService.admin_recycle_user_trial(user=target, note=note)
        except ValueError as exc:
            return error_response(msg=str(exc), code=40001, status_code=status.HTTP_400_BAD_REQUEST)

        _send_membership_pro_notification(
            request=request,
            user_id=target.id,
            business_scene="membership.pro_trial.revoked",
            title="试用已收回",
            body="你的 Pro 模型试用权限已被收回。",
            business_id=str(trial.id),
            channels=[
                NotificationMessage.Channel.APNS,
                NotificationMessage.Channel.EMAIL,
            ],
            status_value="expired",
            application_id=None,
        )

        pro = TrialService.build_pro_summary(user=target)
        payload = {"user_id": target.id, "pro": pro}
        write_audit_log(
            request,
            action="admin.user.pro.recycle",
            resource_type="user",
            resource_id=str(target.id),
            status_code=200,
            response_payload={
                **payload,
                "trial_id": trial.id,
                "previous_status": previous_status,
                "new_status": trial.status,
                "expires_at": trial.expires_at.isoformat() if trial.expires_at else None,
                "note": note,
                "operator_user_id": getattr(request.user, "id", None),
            },
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminDeviceListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = TrustedDevice.objects.select_related("user").all().order_by("-last_seen", "-id")
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(device_id__icontains=query)
                | Q(bundle_id__icontains=query)
                | Q(device_name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(user__email__icontains=query)
            )

        user_id = (request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            queryset = queryset.filter(user_id=int(user_id))

        revoked = (request.query_params.get("is_revoked") or "").strip()
        if revoked in {"true", "false"}:
            queryset = queryset.filter(is_revoked=(revoked == "true"))

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": AdminDeviceSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminDeviceRevokeView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:device:revoke"

    def post(self, request, device_id: int):
        target = get_object_or_404(TrustedDevice.objects.select_related("user"), pk=device_id)
        serializer = AdminDeviceRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target.is_revoked = serializer.validated_data["is_revoked"]
        target.save(update_fields=["is_revoked", "last_seen"])
        payload = AdminDeviceSerializer(target).data
        write_audit_log(
            request,
            action="admin.user.device.revoke.update",
            resource_type="trusted_device",
            resource_id=str(target.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminDeactivationListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = AccountDeactivation.objects.select_related("user").all().order_by("-requested_at", "-id")
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(user__username__icontains=query)
                | Q(user__email__icontains=query)
                | Q(request_id__icontains=query)
            )
        state = (request.query_params.get("state") or "").strip()
        if state:
            queryset = queryset.filter(state=state)
        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": AdminDeactivationSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminDeactivationAuditListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, deactivation_id: int):
        row = get_object_or_404(AccountDeactivation, pk=deactivation_id)
        audits = AccountDeactivationAudit.objects.filter(deactivation=row).order_by("-created_at", "-id")
        payload = AdminDeactivationAuditSerializer(audits, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminDeactivationCancelView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:deactivation:cancel"

    @transaction.atomic
    def post(self, request, deactivation_id: int):
        row = get_object_or_404(AccountDeactivation.objects.select_for_update(), pk=deactivation_id)
        if row.state in {
            AccountDeactivation.DeactivationState.COMPLETED,
            AccountDeactivation.DeactivationState.CANCELLED,
        }:
            return success_response(
                {"deactivation_id": row.id, "state": row.state, "detail": "already_terminal"},
                msg="noop",
                code=0,
                status_code=status.HTTP_200_OK,
            )
        row.state = AccountDeactivation.DeactivationState.CANCELLED
        row.cancelled_at = timezone.now()
        row.save(update_fields=["state", "cancelled_at"])
        AccountDeactivationAudit.objects.create(
            deactivation=row,
            action=AccountDeactivationAudit.AuditAction.CANCELLED,
            request_id=(getattr(request, "request_id", "") or ""),
            details={"by_admin_user_id": getattr(request.user, "id", None)},
        )
        payload = AdminDeactivationSerializer(row).data
        write_audit_log(
            request,
            action="admin.user.deactivation.cancel",
            resource_type="account_deactivation",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminDeactivationRetryView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:user:deactivation:retry"

    @transaction.atomic
    def post(self, request, deactivation_id: int):
        row = get_object_or_404(AccountDeactivation.objects.select_for_update(), pk=deactivation_id)
        if row.state == AccountDeactivation.DeactivationState.CANCELLED:
            return error_response(msg="cannot_retry_cancelled", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        if row.state == AccountDeactivation.DeactivationState.COMPLETED:
            return success_response(
                {"deactivation_id": row.id, "state": row.state, "detail": "already_completed"},
                msg="noop",
                code=0,
                status_code=status.HTTP_200_OK,
            )

        row.state = AccountDeactivation.DeactivationState.SCHEDULED
        row.failed_at = None
        row.error_message = ""
        row.save(update_fields=["state", "failed_at", "error_message"])
        process_deactivation_task.delay(row.id, getattr(request, "request_id", "") or "")
        payload = AdminDeactivationSerializer(row).data
        write_audit_log(
            request,
            action="admin.user.deactivation.retry",
            resource_type="account_deactivation",
            resource_id=str(row.id),
            status_code=202,
            response_payload=payload,
        )
        return success_response(payload, msg="queued", code=0, status_code=status.HTTP_202_ACCEPTED)


class AdminNotificationUserListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        query = AdminNotificationUserQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = NotificationCenterService.list_notification_users(**query.validated_data)
        return success_response(result, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationSendView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:notification:send"

    def post(self, request):
        serializer = AdminNotificationSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        campaign = NotificationCenterService.create_campaign_and_enqueue(
            campaign_name=data.get("campaign_name") or "",
            channels=data["channels"],
            title=data.get("title") or "",
            body=data.get("body") or "",
            payload=data.get("payload") or {},
            user_id=data.get("user_id"),
            user_ids=data.get("user_ids") or [],
            filters=data.get("filters") or {},
            template_id=data.get("template_id"),
            schedule_at=data.get("schedule_at"),
            created_by_id=getattr(request.user, "id", None),
            request_id=(request.headers.get("X-Request-ID") or "").strip(),
        )
        payload = AdminNotificationCampaignSerializer(campaign).data
        write_audit_log(
            request,
            action="admin.notification.campaign.create",
            resource_type="notification_campaign",
            resource_id=str(payload["id"]),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="queued", code=0, status_code=status.HTTP_201_CREATED)


class AdminNotificationLogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, channel: str):
        if channel not in {NotificationMessage.Channel.APNS, NotificationMessage.Channel.EMAIL, NotificationMessage.Channel.SMS}:
            return error_response(msg="invalid_channel", code=40001, status_code=status.HTTP_400_BAD_REQUEST)

        query_serializer = AdminNotificationLogQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        query = query_serializer.validated_data

        queryset = NotificationMessage.objects.select_related("user").filter(channel=channel).order_by("-created_at", "-id")
        search_q = (query.get("q") or "").strip()
        if search_q:
            lookup = (
                Q(user__username__icontains=search_q)
                | Q(user__email__icontains=search_q)
                | Q(title__icontains=search_q)
                | Q(receiver_phone__icontains=search_q)
                | Q(receiver_email__icontains=search_q)
                | Q(provider_message_id__icontains=search_q)
            )
            if "@" in search_q:
                lookup |= Q(channel_deliveries__endpoint_hmac=NotificationCenterService._email_hmac(search_q))
            elif any(ch.isdigit() for ch in search_q):
                normalized_phone = NotificationCenterService._normalize_phone(search_q)
                if normalized_phone:
                    lookup |= Q(channel_deliveries__endpoint_hmac=NotificationCenterService._phone_hmac(normalized_phone))
            queryset = queryset.filter(lookup).distinct()
        if query.get("status"):
            queryset = queryset.filter(status=query["status"])

        page = query["page"]
        page_size = query["page_size"]
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        rows = AdminNotificationMessageSerializer(page_obj.object_list, many=True).data
        payload = {
            "items": rows,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationLogDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, log_id: int):
        row = get_object_or_404(NotificationMessage.objects.select_related("user"), pk=log_id)
        payload = AdminNotificationMessageSerializer(row).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationTemplateListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = NotificationCenterService.list_templates()
        payload = AdminNotificationTemplateSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminNotificationTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        payload = AdminNotificationTemplateSerializer(row).data
        write_audit_log(
            request,
            action="admin.notification.template.create",
            resource_type="notification_template",
            resource_id=str(row.id),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminNotificationTemplateDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, template_id: int):
        row = get_object_or_404(NotificationTemplate, pk=template_id)
        serializer = AdminNotificationTemplateSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = AdminNotificationTemplateSerializer(row).data
        write_audit_log(
            request,
            action="admin.notification.template.update",
            resource_type="notification_template",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def delete(self, request, template_id: int):
        row = get_object_or_404(NotificationTemplate, pk=template_id)
        row.delete()
        write_audit_log(
            request,
            action="admin.notification.template.delete",
            resource_type="notification_template",
            resource_id=str(template_id),
            status_code=200,
            response_payload={},
        )
        return success_response({}, msg="deleted", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationPreviewView(APIView):
    permission_classes = [AdminOnlyPermission]

    def post(self, request):
        serializer = AdminNotificationTemplatePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        user_id = data.get("user_id")
        if user_id:
            user = get_object_or_404(User, pk=user_id)

        template = None
        if data.get("template_id"):
            template = get_object_or_404(NotificationTemplate, pk=data["template_id"])

        title, body, payload = NotificationCenterService.build_message_content(
            user=user,
            template=template,
            title=data.get("title") or "",
            body=data.get("body") or "",
            payload=data.get("payload") or {},
        )
        result = {
            "title": title,
            "body": body,
            "payload": payload,
            "context": NotificationCenterService.build_context_for_user(user),
        }
        return success_response(result, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationCampaignListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = NotificationCampaign.objects.select_related("created_by", "template").order_by("-created_at", "-id")
        q = (request.query_params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(title__icontains=q))
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": AdminNotificationCampaignSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAppVersionConfigListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = AppVersionConfig.objects.select_related("created_by").all()
        platform = (request.query_params.get("platform") or "").strip()
        channel = (request.query_params.get("channel") or "").strip()
        bundle_id = (request.query_params.get("bundle_id") or "").strip()
        is_active = request.query_params.get("is_active")
        if platform:
            queryset = queryset.filter(platform=platform)
        if channel:
            queryset = queryset.filter(channel=channel)
        if bundle_id:
            queryset = queryset.filter(bundle_id__icontains=bundle_id)
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))
        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        return success_response(
            {
                "items": AppVersionConfigSerializer(page_obj.object_list, many=True).data,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                },
            },
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )

    def post(self, request):
        if not request.user.is_superuser and "button:version:config:create" not in get_user_permission_codes(request.user.id):
            return error_response(msg="permission_denied", code=40303, status_code=status.HTTP_403_FORBIDDEN)
        serializer = AppVersionConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(created_by=request.user)
        write_audit_log(request, action="version.config.create", resource_type="app_version_config", resource_id=str(obj.id), status_code=201)
        return success_response(AppVersionConfigSerializer(obj).data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminAppVersionConfigDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:version:config:update"

    def patch(self, request, config_id: int):
        obj = get_object_or_404(AppVersionConfig, pk=config_id)
        serializer = AppVersionConfigSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        write_audit_log(request, action="version.config.update", resource_type="app_version_config", resource_id=str(obj.id), status_code=200)
        return success_response(AppVersionConfigSerializer(obj).data, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def delete(self, request, config_id: int):
        obj = get_object_or_404(AppVersionConfig, pk=config_id)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        write_audit_log(request, action="version.config.disable", resource_type="app_version_config", resource_id=str(obj.id), status_code=200)
        return success_response({"success": True}, msg="disabled", code=0, status_code=status.HTTP_200_OK)


class AdminVersionCheckLogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = VersionCheckLog.objects.select_related("user", "config").all()
        q = (request.query_params.get("q") or "").strip()
        platform = (request.query_params.get("platform") or "").strip()
        bundle_id = (request.query_params.get("bundle_id") or "").strip()
        has_update = request.query_params.get("has_update")
        force_update = request.query_params.get("force_update")
        if q:
            queryset = queryset.filter(
                Q(device_id__icontains=q)
                | Q(current_version__icontains=q)
                | Q(latest_version__icontains=q)
                | Q(request_id__icontains=q)
            )
        if platform:
            queryset = queryset.filter(platform=platform)
        if bundle_id:
            queryset = queryset.filter(bundle_id__icontains=bundle_id)
        if has_update in {"true", "false"}:
            queryset = queryset.filter(has_update=(has_update == "true"))
        if force_update in {"true", "false"}:
            queryset = queryset.filter(force_update=(force_update == "true"))
        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        return success_response(
            {
                "items": VersionCheckLogSerializer(page_obj.object_list, many=True).data,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                },
            },
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )


SCENARIO_LABEL_ZH = {
    "chat": "对话",
    "embedding": "向量模型",
    "voice": "语音模型",
    "medical_structured_extraction": "医疗文档结构化抽取",
    "medical_document_type_recognition": "医疗文档类型识别",
    "medical_case_extraction": "病例结构化抽取",
    "health_exam_extraction": "体检报告结构化抽取",
    "medical_report_extraction": "医疗报告结构化抽取",
    "prescription_extraction": "处方结构化抽取",
    "medication_extraction": "用药结构化抽取",
    "medicine_box_extraction": "药品结构化抽取",
    "optimization_text": "文本优化模型",
    "optimization_visual": "视觉优化模型",
    "context_folding": "上下文折叠",
    "router": "Router 模型",
    "model_config": "模型配置",
    "report_interpretation": "报告解读模型",
}


def _scenario_key_valid(scenario_key: str) -> bool:
    return scenario_key in {m.value for m in ScenarioKey}


class AdminAIScenarioSummaryListView(APIView):
    """Aggregate counts and default model for each configured scenario."""

    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows_out = []
        for member in ScenarioKey:
            key = member.value
            qs = AIScenarioModelBinding.objects.filter(scenario=key)
            active = qs.filter(is_active=True).order_by("position", "id")
            default_row = active.filter(is_default=True).first()
            rows_out.append(
                {
                    "scenario": key,
                    "label": SCENARIO_LABEL_ZH.get(key, key),
                    "models_count": qs.count(),
                    "default_model": default_row.bootstrap_name() if default_row else None,
                    "active_bindings": active.count(),
                }
            )
        return success_response(rows_out, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAIToolOptionsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = [{"value": item.value, "label": item.label} for item in SparkToolName]
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAIScenarioBindingListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, scenario_key: str):
        if not _scenario_key_valid(scenario_key):
            return error_response(msg="invalid_scenario", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        rows = (
            AIScenarioModelBinding.objects.select_related("model")
            .filter(scenario=scenario_key)
            .order_by("position", "id")
        )
        payload = AdminAIScenarioModelBindingSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request, scenario_key: str):
        permission_codes = get_user_permission_codes(request.user.id)
        if not request.user.is_superuser and "button:ai:scenario:create" not in permission_codes:
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        if not _scenario_key_valid(scenario_key):
            return error_response(msg="invalid_scenario", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        serializer = AdminAIScenarioModelBindingSerializer(data=request.data, context={"scenario": scenario_key})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
        payload = serializer.data
        write_audit_log(
            request,
            action="admin.ai.scenario_binding.create",
            resource_type="ai_scenario_binding",
            resource_id=str(payload["id"]),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminAIScenarioBindingDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:scenario:update"

    def patch(self, request, binding_id: int):
        row = get_object_or_404(AIScenarioModelBinding, pk=binding_id)
        serializer = AdminAIScenarioModelBindingSerializer(row, data=request.data, partial=True, context={"scenario": row.scenario})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
        payload = serializer.data
        write_audit_log(
            request,
            action="admin.ai.scenario_binding.update",
            resource_type="ai_scenario_binding",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def delete(self, request, binding_id: int):
        row = get_object_or_404(AIScenarioModelBinding, pk=binding_id)
        others = AIScenarioModelBinding.objects.filter(scenario=row.scenario).exclude(pk=row.pk)
        if not others.exists():
            return error_response(msg="cannot_delete_last_binding", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            was_default = row.is_default
            row.delete()
            if was_default:
                nxt = others.filter(is_active=True).order_by("position", "id").first() or others.order_by("position", "id").first()
                if nxt and not AIScenarioModelBinding.objects.filter(scenario=nxt.scenario, is_default=True).exists():
                    nxt.is_default = True
                    nxt.save()
        write_audit_log(
            request,
            action="admin.ai.scenario_binding.delete",
            resource_type="ai_scenario_binding",
            resource_id=str(binding_id),
            status_code=200,
            response_payload={},
        )
        return success_response({}, msg="deleted", code=0, status_code=status.HTTP_200_OK)


class AdminAIModelCatalogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = AIModelCatalog.objects.all().order_by("position", "name")
        payload = AdminAIModelCatalogSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        permission_codes = get_user_permission_codes(request.user.id)
        if not request.user.is_superuser and "button:ai:model:create" not in permission_codes:
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        serializer = AdminAIModelCatalogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        payload = AdminAIModelCatalogSerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.model_catalog.create",
            resource_type="ai_model_catalog",
            resource_id=str(row.id),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminAIModelCatalogDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:model:update"

    def patch(self, request, catalog_id: int):
        row = get_object_or_404(AIModelCatalog, pk=catalog_id)
        serializer = AdminAIModelCatalogUpdateSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = AdminAIModelCatalogSerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.model_catalog.update",
            resource_type="ai_model_catalog",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminSmallTaskListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = SmallTask.objects.filter(is_deleted=False).order_by("source", "id")
        payload = AdminSmallTaskSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        permission_codes = get_user_permission_codes(request.user.id)
        if not request.user.is_superuser and "button:ai:small_task:create" not in permission_codes:
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        data = request.data.copy()
        data.setdefault("source", SmallTask.Source.SERVICE)
        serializer = AdminSmallTaskSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        payload = AdminSmallTaskSerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.small_task.create",
            resource_type="ai_small_task",
            resource_id=str(row.id),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminSmallTaskDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:small_task:update"

    def patch(self, request, task_id: int):
        row = get_object_or_404(SmallTask, pk=task_id, is_deleted=False)
        serializer = AdminSmallTaskSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = AdminSmallTaskSerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.small_task.update",
            resource_type="ai_small_task",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def delete(self, request, task_id: int):
        row = get_object_or_404(SmallTask, pk=task_id, is_deleted=False)
        row.is_deleted = True
        row.save(update_fields=["is_deleted", "updated_at"])
        write_audit_log(
            request,
            action="admin.ai.small_task.delete",
            resource_type="ai_small_task",
            resource_id=str(task_id),
            status_code=200,
            response_payload={},
        )
        return success_response({}, msg="deleted", code=0, status_code=status.HTTP_200_OK)


class AdminAIProviderKeyListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        kind = (request.query_params.get("kind") or "").strip()
        queryset = AIProviderKeyConfig.objects.all().order_by("kind", "position", "company", "name")
        if kind:
            queryset = queryset.filter(kind=kind)
        payload = AdminAIProviderKeySerializer(queryset, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        permission_codes = get_user_permission_codes(request.user.id)
        if not request.user.is_superuser and "button:ai:provider:create" not in permission_codes:
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)
        serializer = AdminAIProviderKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        payload = AdminAIProviderKeySerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.provider.create",
            resource_type="ai_provider",
            resource_id=str(row.id),
            status_code=201,
            response_payload=payload,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminAIProviderKeyDetailView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:provider:update"

    def patch(self, request, provider_id: int):
        row = get_object_or_404(AIProviderKeyConfig, pk=provider_id)
        serializer = AdminAIProviderKeyUpdateSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = AdminAIProviderKeySerializer(row).data
        write_audit_log(
            request,
            action="admin.ai.provider.update",
            resource_type="ai_provider",
            resource_id=str(row.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminAITrialListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = (
            TrialApplication.objects.select_related("user")
            .prefetch_related(
                Prefetch(
                    "user__trusted_devices",
                    queryset=TrustedDevice.objects.order_by("-last_seen", "-id"),
                ),
                Prefetch(
                    "user__trial_application_requests",
                    queryset=TrialApplicationRequest.objects.order_by("-created_at", "-id"),
                ),
            )
            .all()
            .order_by("-created_at", "-id")
        )
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        payload = {
            "items": AdminTrialApplicationSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAITrialDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, trial_id: int):
        row = get_object_or_404(
            TrialApplication.objects.select_related("user").prefetch_related(
                Prefetch(
                    "user__trusted_devices",
                    queryset=TrustedDevice.objects.order_by("-last_seen", "-id"),
                ),
                Prefetch(
                    "user__trial_application_requests",
                    queryset=TrialApplicationRequest.objects.order_by("-created_at", "-id"),
                ),
            ),
            pk=trial_id,
        )
        payload = AdminTrialApplicationSerializer(row).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAITrialActionView(APIView):
    # 权限码与动作绑定（approve/reject/recycle/grant），这里不使用 AdminCodePermission 的单码校验。
    permission_classes = [AdminOnlyPermission]

    @transaction.atomic
    def post(self, request, trial_id: int, action: str):
        trial = get_object_or_404(TrialApplication.objects.select_for_update(), pk=trial_id)
        serializer = AdminTrialActionSerializer(data=request.data, context={"action": action})
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "").strip()

        now = timezone.now()
        if action == "approve":
            trial.status = TrialApplication.Status.ACTIVE
            trial.grant_source = TrialApplication.GrantSource.MANUAL
            trial.started_at = now
            trial.expires_at = now + timedelta(days=TrialService._trial_days())
            trial.approved_at = now
            trial.rejected_at = None
            required_code = "button:ai:trial:approve"
        elif action == "reject":
            trial.status = TrialApplication.Status.REJECTED
            trial.grant_source = TrialApplication.GrantSource.MANUAL
            trial.rejected_at = now
            trial.approved_at = None
            required_code = "button:ai:trial:reject"
        elif action == "recycle":
            required_code = "button:ai:trial:recycle"
        elif action == "grant":
            required_code = "button:ai:trial:grant"
        else:
            return error_response(msg="invalid_action", code=40001, status_code=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_superuser and required_code not in get_user_permission_codes(request.user.id):
            return error_response(msg="permission_denied", code=40301, status_code=status.HTTP_403_FORBIDDEN)

        if action == "recycle":
            try:
                trial, _previous_status = TrialService.admin_recycle_user_trial(user=trial.user, note=note)
            except ValueError as exc:
                return error_response(msg=str(exc), code=40001, status_code=status.HTTP_400_BAD_REQUEST)
            payload = AdminTrialApplicationSerializer(trial).data
            write_audit_log(
                request,
                action=f"admin.ai.trial.{action}",
                resource_type="trial_application",
                resource_id=str(trial.id),
                status_code=200,
                response_payload=payload,
            )
            return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

        if action == "grant":
            try:
                trial, grant_req, _previous_status = TrialService.admin_grant_user_trial(
                    user=trial.user,
                    grant_days=serializer.validated_data.get("grant_days"),
                    expires_at=serializer.validated_data.get("expires_at"),
                    note=note,
                )
            except ValueError as exc:
                return error_response(msg=str(exc), code=40001, status_code=status.HTTP_400_BAD_REQUEST)
            try:
                NotificationCenterService.send_to_user_sync(
                    campaign_id=None,
                    user_id=trial.user_id,
                    channels=[
                        NotificationMessage.Channel.APNS,
                        NotificationMessage.Channel.EMAIL,
                        NotificationMessage.Channel.SMS,
                    ],
                    title="已发放 Pro 试用权限",
                    body="系统已为你发放 Pro 模型试用权限。",
                    payload={
                        "type": "ai_trial_application_result",
                        "status": "active",
                        "application_id": grant_req.id,
                        "refresh_ai_config": True,
                        "route": "ai_settings",
                    },
                    created_by_id=getattr(request.user, "id", None),
                    request_id=getattr(request, "request_id", "") or "",
                    business_scene="membership.pro_trial.manually_granted",
                    business_reference_type="trial_application",
                    business_id=str(grant_req.id),
                    idempotency_key=f"membership.pro_trial.manually_granted:{grant_req.id}:manual",
                    source="backoffice.ai_trial",
                    actor_type="admin",
                    actor_id=str(getattr(request.user, "id", "") or ""),
                )
            except Exception:
                pass
            payload = AdminTrialApplicationSerializer(trial).data
            write_audit_log(
                request,
                action=f"admin.ai.trial.{action}",
                resource_type="trial_application",
                resource_id=str(trial.id),
                status_code=200,
                response_payload=payload,
            )
            return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

        if note:
            trial.note = note
        trial.save()

        # 同步申请流水（若存在 pending 流水则标记为通过/拒绝），并对通过/拒绝发送 APNs 通知。
        pending_req = (
            TrialApplicationRequest.objects.select_for_update()
            .filter(
                user_id=trial.user_id,
                source=TrialApplicationRequest.Source.APPLICATION,
                status=TrialApplication.Status.PENDING,
            )
            .order_by("-sequence")
            .first()
        )
        if action == "approve":
            if pending_req:
                pending_req.status = TrialApplication.Status.ACTIVE
                pending_req.approved_at = now
                pending_req.rejected_at = None
                pending_req.save(update_fields=["status", "approved_at", "rejected_at", "updated_at"])
            try:
                NotificationCenterService.send_to_user_sync(
                    campaign_id=None,
                    user_id=trial.user_id,
                    channels=[
                        NotificationMessage.Channel.APNS,
                        NotificationMessage.Channel.EMAIL,
                        NotificationMessage.Channel.SMS,
                    ],
                    title="试用申请已通过",
                    body="你的 Pro 模型试用申请已通过，现在可以使用服务端模型。",
                    payload={
                        "type": "ai_trial_application_result",
                        "status": "active",
                        "application_id": pending_req.id if pending_req else None,
                        "refresh_ai_config": True,
                        "route": "ai_settings",
                    },
                    created_by_id=getattr(request.user, "id", None),
                    request_id=getattr(request, "request_id", "") or "",
                    business_scene="membership.pro_trial.application_approved",
                    business_reference_type="trial_application",
                    business_id=str(pending_req.id if pending_req else trial.id),
                    idempotency_key=f"membership.pro_trial.application_approved:{pending_req.id if pending_req else trial.id}:manual",
                    source="backoffice.ai_trial",
                    actor_type="admin",
                    actor_id=str(getattr(request.user, "id", "") or ""),
                )
            except Exception:
                # 通知失败不影响人工审核结果
                pass
        elif action == "reject":
            if pending_req:
                pending_req.status = TrialApplication.Status.REJECTED
                pending_req.rejected_at = now
                pending_req.approved_at = None
                pending_req.save(update_fields=["status", "rejected_at", "approved_at", "updated_at"])
            try:
                NotificationCenterService.send_to_user_sync(
                    campaign_id=None,
                    user_id=trial.user_id,
                    channels=[NotificationMessage.Channel.APNS],
                    title="试用申请未通过",
                    body="你的 Pro 模型试用申请未通过。",
                    payload={
                        "type": "ai_trial_application_result",
                        "status": "rejected",
                        "application_id": pending_req.id if pending_req else None,
                        "refresh_ai_config": True,
                        "route": "ai_settings",
                    },
                    created_by_id=getattr(request.user, "id", None),
                    request_id=getattr(request, "request_id", "") or "",
                    business_scene="membership.pro_trial.application_rejected",
                    business_reference_type="trial_application",
                    business_id=str(pending_req.id if pending_req else trial.id),
                    idempotency_key=f"membership.pro_trial.application_rejected:{pending_req.id if pending_req else trial.id}:manual",
                    source="backoffice.ai_trial",
                    actor_type="admin",
                    actor_id=str(getattr(request.user, "id", "") or ""),
                )
            except Exception:
                pass

        payload = AdminTrialApplicationSerializer(trial).data
        write_audit_log(
            request,
            action=f"admin.ai.trial.{action}",
            resource_type="trial_application",
            resource_id=str(trial.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminAsyncTaskDashboardView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        window_hours = int(request.query_params.get("window_hours", "24") or "24")
        window_hours = max(1, min(window_hours, 168))
        limit = int(request.query_params.get("limit", "20") or "20")
        limit = max(1, min(limit, 100))

        since = timezone.now() - timedelta(hours=window_hours)
        recent = TaskResult.objects.filter(date_done__gte=since)

        aggregate = recent.aggregate(
            total_recent=Count("id"),
            success=Count("id", filter=Q(status="SUCCESS")),
            failure=Count("id", filter=Q(status="FAILURE")),
            pending=Count("id", filter=Q(status="PENDING")),
            started=Count("id", filter=Q(status="STARTED")),
            retry=Count("id", filter=Q(status="RETRY")),
            revoked=Count("id", filter=Q(status="REVOKED")),
        )
        total_recent = int(aggregate.get("total_recent") or 0)
        failed = int(aggregate.get("failure") or 0)
        status_counter = {
            "success": int(aggregate.get("success") or 0),
            "failure": failed,
            "pending": int(aggregate.get("pending") or 0),
            "started": int(aggregate.get("started") or 0),
            "retry": int(aggregate.get("retry") or 0),
            "revoked": int(aggregate.get("revoked") or 0),
        }

        def _business_metrics(task_name_fragments: list[str]) -> dict:
            condition = Q()
            for fragment in task_name_fragments:
                condition |= Q(task_name__icontains=fragment)
            scoped = recent.filter(condition)
            scoped_agg = scoped.aggregate(
                total=Count("id"),
                success=Count("id", filter=Q(status="SUCCESS")),
                failure=Count("id", filter=Q(status="FAILURE")),
                pending=Count("id", filter=Q(status="PENDING")),
                started=Count("id", filter=Q(status="STARTED")),
                retry=Count("id", filter=Q(status="RETRY")),
            )
            return {
                "total": int(scoped_agg.get("total") or 0),
                "success": int(scoped_agg.get("success") or 0),
                "failure": int(scoped_agg.get("failure") or 0),
                "running": int(scoped_agg.get("pending") or 0)
                + int(scoped_agg.get("started") or 0)
                + int(scoped_agg.get("retry") or 0),
            }

        notification_counter = _business_metrics(
            ["send_notification_campaign_task", "notification_tasks.send_notification_campaign_task"]
        )
        deactivation_counter = _business_metrics(
            ["process_deactivation_task", "deactivation.tasks.process_deactivation_task"]
        )

        periodic_total = PeriodicTask.objects.count()
        periodic_enabled = PeriodicTask.objects.filter(enabled=True).count()
        periodic_disabled = max(periodic_total - periodic_enabled, 0)

        latest_tasks = list(
            TaskResult.objects.order_by("-date_done")
            .values("task_id", "task_name", "status", "date_done", "result", "traceback")[:limit]
        )
        for row in latest_tasks:
            result_str = str(row.get("result") or "")
            traceback_str = str(row.get("traceback") or "")
            row["result_preview"] = (result_str[:120] + "...") if len(result_str) > 120 else result_str
            row["has_traceback"] = bool(traceback_str)

        failure_rate = round((failed / total_recent) * 100, 2) if total_recent > 0 else 0.0
        running_like = status_counter["pending"] + status_counter["started"] + status_counter["retry"]
        payload = {
            "summary": {
                "window_hours": window_hours,
                "total_recent": total_recent,
                "status_counter": status_counter,
                "periodic_total": periodic_total,
                "periodic_enabled": periodic_enabled,
                "periodic_disabled": periodic_disabled,
                "failure_rate": failure_rate,
                "running_like": running_like,
                "business_counter": {
                    "notification": notification_counter,
                    "deactivation": deactivation_counter,
                },
            },
            "recent_tasks": latest_tasks,
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAsyncTaskManagerStatusView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = _get_celery_runtime_status()
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminAsyncTaskManagerControlView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:tasks:manager:control"

    def post(self, request, action: str):
        action = (action or "").strip().lower()
        if action not in {"start", "stop", "restart", "start_redis", "stop_redis"}:
            return error_response(msg="invalid_action", code=40001, status_code=status.HTTP_400_BAD_REQUEST)

        if action == "start_redis":
            operations = [_try_start_local_redis()]
            payload = {
                "action": action,
                "operations": operations,
                "status": _get_celery_runtime_status(),
            }
            write_audit_log(
                request,
                action="admin.tasks.manager.start_redis",
                resource_type="celery_runtime",
                status_code=200,
                response_payload=payload,
            )
            return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

        if action == "stop_redis":
            operations = [_try_stop_local_redis()]
            payload = {
                "action": action,
                "operations": operations,
                "status": _get_celery_runtime_status(),
            }
            write_audit_log(
                request,
                action="admin.tasks.manager.stop_redis",
                resource_type="celery_runtime",
                status_code=200,
                response_payload=payload,
            )
            return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

        # Keep the worker subscribed to every routed notification queue.  A
        # worker without -Q only consumes the default ``celery`` queue, which
        # leaves notification outbox rows stuck in PROCESSING forever after
        # the task router sends them to their dedicated queues.
        celery_worker_cmd = [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "SparkService",
            "worker",
            "--loglevel=INFO",
            "-Q",
            ",".join(_celery_worker_queue_names()),
        ]
        celery_beat_cmd = [sys.executable, "-m", "celery", "-A", "SparkService", "beat", "--loglevel=INFO"]

        operations: list[dict] = []
        if action in {"stop", "restart"}:
            operations.append(_stop_process("celery_beat.pid", "celery_beat"))
            operations.append(_stop_process("celery_worker.pid", "celery_worker"))

        if action in {"start", "restart"}:
            operations.append(_start_process_if_needed("celery_worker.pid", "celery_worker", celery_worker_cmd))
            operations.append(_start_process_if_needed("celery_beat.pid", "celery_beat", celery_beat_cmd))

        payload = {
            "action": action,
            "operations": operations,
            "status": _get_celery_runtime_status(),
        }
        write_audit_log(
            request,
            action=f"admin.tasks.manager.{action}",
            resource_type="celery_runtime",
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminRoleListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = AdminRole.objects.all().order_by("name", "id")
        payload = AdminRoleSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = serializer.data
        write_audit_log(request, action="admin.rbac.role.create", resource_type="role", resource_id=str(payload["id"]), status_code=201)
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminRoleDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, role_id: int):
        row = get_object_or_404(AdminRole, pk=role_id)
        serializer = AdminRoleSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = serializer.data
        write_audit_log(request, action="admin.rbac.role.update", resource_type="role", resource_id=str(row.id), status_code=200)
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminPermissionListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = AdminPermission.objects.all().order_by("permission_type", "code", "id")
        payload = AdminPermissionSerializer(rows, many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminPermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        payload = serializer.data
        write_audit_log(
            request,
            action="admin.rbac.permission.create",
            resource_type="permission",
            resource_id=str(payload["id"]),
            status_code=201,
        )
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminRolePermissionAssignView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, role_id: int):
        role = get_object_or_404(AdminRole, pk=role_id)
        codes = list(
            AdminRolePermission.objects.filter(role=role)
            .select_related("permission")
            .values_list("permission__code", flat=True)
        )
        return success_response(
            {"role_id": role.id, "permission_codes": codes},
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )

    @transaction.atomic
    def post(self, request, role_id: int):
        role = get_object_or_404(AdminRole, pk=role_id)
        serializer = AdminRolePermissionAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        codes = serializer.validated_data["permission_codes"]
        rows = list(AdminPermission.objects.filter(code__in=codes))
        mapping = {row.code: row for row in rows}

        AdminRolePermission.objects.filter(role=role).exclude(permission__code__in=codes).delete()
        for code in codes:
            permission = mapping.get(code)
            if permission is None:
                continue
            AdminRolePermission.objects.get_or_create(role=role, permission=permission)

        payload = {"role_id": role.id, "permission_codes": codes}
        write_audit_log(request, action="admin.rbac.role.permission.assign", resource_type="role", resource_id=str(role.id), response_payload=payload)
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminUserRoleAssignView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:rbac:role:assign"

    @transaction.atomic
    def post(self, request, user_id: int):
        target = get_object_or_404(User, pk=user_id)
        serializer = AdminUserRoleAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role_codes = serializer.validated_data["role_codes"]
        rows = list(AdminRole.objects.filter(code__in=role_codes))
        mapping = {row.code: row for row in rows}

        AdminUserRole.objects.filter(user=target).exclude(role__code__in=role_codes).delete()
        for code in role_codes:
            role = mapping.get(code)
            if role is None:
                continue
            AdminUserRole.objects.get_or_create(user=target, role=role)

        payload = {"user_id": target.id, "role_codes": role_codes}
        write_audit_log(
            request,
            action="admin.rbac.user.role.assign",
            resource_type="user",
            resource_id=str(target.id),
            status_code=200,
            response_payload=payload,
        )
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class AdminAuditLogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = AdminAuditLog.objects.select_related("user").all().order_by("-created_at", "-id")
        action = (request.query_params.get("action") or "").strip()
        if action:
            queryset = queryset.filter(action__icontains=action)

        resource_type = (request.query_params.get("resource_type") or "").strip()
        if resource_type:
            queryset = queryset.filter(resource_type__icontains=resource_type)

        request_id = (request.query_params.get("request_id") or "").strip()
        if request_id:
            queryset = queryset.filter(request_id=request_id)

        path = (request.query_params.get("path") or "").strip()
        if path:
            queryset = queryset.filter(path__icontains=path)

        user_id = (request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            queryset = queryset.filter(user_id=int(user_id))

        status_code = (request.query_params.get("status_code") or "").strip()
        if status_code.isdigit():
            queryset = queryset.filter(status_code=int(status_code))

        date_from = (request.query_params.get("date_from") or "").strip()
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        date_to = (request.query_params.get("date_to") or "").strip()
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        payload = {
            "items": AdminAuditLogSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
