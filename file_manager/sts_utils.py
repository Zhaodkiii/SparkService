"""
阿里云 OSS STS 临时凭证（与 ZhaodkDream 行为对齐；服务端独占长期 AK）。
配置统一从 Django settings 读取（settings 由 `.env` / 环境变量在 SparkService/settings.py 中注入）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from aliyunsdkcore.client import AcsClient
    from aliyunsdksts.request.v20150401 import AssumeRoleRequest

    ALIYUN_SDK_AVAILABLE = True
except ImportError:
    ALIYUN_SDK_AVAILABLE = False
    logger.warning("阿里云 SDK 未安装，STS 功能将不可用")


def _endpoint_url(region: str) -> str:
    explicit = (getattr(settings, "ALIYUN_OSS_ENDPOINT", "") or "").strip()
    if explicit:
        return explicit
    return f"https://oss-{region}.aliyuncs.com"


def get_sts_credentials(
    access_key_id: Optional[str] = None,
    access_key_secret: Optional[str] = None,
    role_arn: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    bucket_name: Optional[str] = None,
    region: Optional[str] = None,
) -> Dict[str, Any]:
    access_key_id = access_key_id or settings.ALIYUN_ACCESS_KEY_ID
    access_key_secret = access_key_secret or settings.ALIYUN_ACCESS_KEY_SECRET
    role_arn = (role_arn if role_arn is not None else settings.ALIYUN_STS_ROLE_ARN) or ""
    bucket_name = bucket_name or settings.ALIYUN_OSS_BUCKET
    region = region or settings.ALIYUN_OSS_REGION
    if duration_seconds is None:
        duration_seconds = settings.ALIYUN_STS_DURATION_SECONDS

    if not access_key_id or not access_key_secret:
        raise ValueError(
            "阿里云 AccessKey 未配置：请在 `.env` 中设置 ALIYUN_ACCESS_KEY_ID / "
            "ALIYUN_ACCESS_KEY_SECRET（经 Django settings 加载）"
        )

    if not role_arn:
        logger.warning("未配置 ALIYUN_STS_ROLE_ARN，返回静态凭证（仅用于开发环境）")
        endpoint = _endpoint_url(region)
        expiration_utc = datetime.now(timezone.utc) + timedelta(seconds=int(duration_seconds))
        expiration_timestamp = int(expiration_utc.timestamp())
        return {
            "access_key_id": access_key_id,
            "access_key_secret": access_key_secret,
            "security_token": "",
            "expiration": expiration_timestamp,
            "bucket_name": bucket_name,
            "region": region,
            "endpoint": endpoint,
        }

    if not ALIYUN_SDK_AVAILABLE:
        raise RuntimeError(
            "阿里云 SDK 未安装，无法使用 STS。请安装: "
            "aliyun-python-sdk-core aliyun-python-sdk-sts"
        )

    try:
        client = AcsClient(access_key_id, access_key_secret, region)
        request = AssumeRoleRequest.AssumeRoleRequest()
        request.set_RoleArn(role_arn)
        request.set_RoleSessionName(f"spark-oss-{datetime.now(timezone.utc).timestamp()}")
        request.set_DurationSeconds(int(duration_seconds))

        policy = {
            "Version": "1",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "oss:PutObject",
                        "oss:GetObject",
                        "oss:DeleteObject",
                        "oss:ListObjects",
                        "oss:ListParts",
                        "oss:AbortMultipartUpload",
                        "oss:GetObjectMeta",
                    ],
                    "Resource": [
                        f"acs:oss:*:*:{bucket_name}",
                        f"acs:oss:*:*:{bucket_name}/*",
                    ],
                }
            ],
        }
        request.set_Policy(json.dumps(policy))

        response = client.do_action_with_exception(request)
        result = json.loads(response.decode("utf-8"))
        credentials = result.get("Credentials", {})
        endpoint = _endpoint_url(region)

        expiration_iso = credentials.get("Expiration")
        expiration_timestamp: Optional[int] = None
        if expiration_iso:
            try:
                iso = expiration_iso.replace("Z", "+00:00")
                expiration_dt_utc = datetime.fromisoformat(iso)
                if expiration_dt_utc.tzinfo is None:
                    expiration_dt_utc = expiration_dt_utc.replace(tzinfo=timezone.utc)
                expiration_timestamp = int(expiration_dt_utc.timestamp())
            except (ValueError, AttributeError):
                logger.warning("无法解析过期时间: %s，使用回退时间", expiration_iso)
                fallback_utc = datetime.now(timezone.utc) + timedelta(seconds=int(duration_seconds))
                expiration_timestamp = int(fallback_utc.timestamp())

        return {
            "access_key_id": credentials.get("AccessKeyId"),
            "access_key_secret": credentials.get("AccessKeySecret"),
            "security_token": credentials.get("SecurityToken") or "",
            "expiration": expiration_timestamp,
            "bucket_name": bucket_name,
            "region": region,
            "endpoint": endpoint,
        }
    except Exception as e:
        logger.exception("获取 STS 凭证失败")
        raise RuntimeError(f"获取 STS 凭证失败: {e}") from e
