"""Invitation-only OTP: never signs in, creates an account, or confirms conversion."""
from datetime import timedelta
import re
import secrets
import uuid
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, Throttled
from accounts.infrastructure.sms_provider import AliyunSMSProvider
from .models import InvitationOTP
from . import invitations as svc


def contact_value(kind, contact):
    if kind == 'phone' and not re.fullmatch(r'(?:\+86)?1[3-9][0-9]{9}', contact.strip()):
        raise ValidationError('请输入中国大陆手机号；其他地区请使用邮箱登记')
    return svc.normalize(kind, contact)


def check_link(link):
    if not svc.available(link.campaign) or not link.owner.is_active:
        raise ValidationError('活动已结束或暂停，暂不可登记')


def request_code(link, kind, contact):
    check_link(link)
    value = contact_value(kind, contact)
    digest = svc.contact_digest(kind, value)
    now = timezone.now()
    delivered = False
    # The unique contact row and lock serialize resends even across different links.
    with transaction.atomic():
        InvitationOTP.objects.get_or_create(contact_hash=digest, defaults=dict(
            link=link, expires_at=now, window_started_at=now))
        otp = InvitationOTP.objects.select_for_update().get(pk=digest)
        if otp.sent_at and (now - otp.sent_at).total_seconds() < 60:
            raise Throttled(wait=60, detail='发送太频繁，请稍后重试')
        if now - otp.window_started_at >= timedelta(hours=24):
            otp.window_started_at, otp.send_count = now, 0
        if otp.send_count >= 10:
            raise Throttled(detail='今天发送次数已达上限，请明天再试')
        code = f'{secrets.randbelow(1000000):06d}'
        otp.link, otp.challenge_id = link, uuid.uuid4()
        otp.sent_at, otp.expires_at = now, now + timedelta(minutes=5)
        otp.send_count += 1
        otp.attempts, otp.consumed_at, otp.code_hash = 0, None, ''
        try:
            if kind == 'phone':
                if not AliyunSMSProvider.otp_readiness_error():
                    result = AliyunSMSProvider.send_login_code(phone_number=value, code=code)
                    delivered = result.accepted and not result.unknown
            else:
                # A console/dummy backend must never claim an email was delivered.
                backend = settings.EMAIL_BACKEND
                if backend not in {'django.core.mail.backends.console.EmailBackend',
                                    'django.core.mail.backends.dummy.EmailBackend',
                                    'django.core.mail.backends.filebased.EmailBackend'}:
                    delivered = send_mail('寻寻仔 · 邀请登记验证码',
                        f'你的验证码是 {code}，5 分钟内有效。\n用于验证旅行手帐邀请登记，请勿转发。\n如果不是你本人操作，请忽略此邮件。',
                        settings.DEFAULT_FROM_EMAIL, [value], fail_silently=False) == 1
        except Exception:
            # Do not expose provider details, contacts, or OTP values to the client/logs.
            delivered = False
        if delivered:
            otp.code_hash = make_password(code)
        otp.save()
    if not delivered:
        raise ValidationError('验证码暂未发送成功，请稍后重试')
    return dict(challenge_id=str(otp.challenge_id), resend_after=60, expires_in=300)


def verify_and_register(link, kind, contact, challenge_id, code):
    check_link(link)
    value = contact_value(kind, contact)
    digest = svc.contact_digest(kind, value)
    error = None
    registration = None
    with transaction.atomic():
        otp = InvitationOTP.objects.select_for_update().filter(pk=digest, link=link, challenge_id=challenge_id).first()
        now = timezone.now()
        if not otp or not otp.code_hash or otp.consumed_at or otp.expires_at <= now:
            error = '验证码已失效，请重新获取'
        elif otp.attempts >= 5:
            error = '验证码错误次数过多，请重新获取'
        elif not check_password(code, otp.code_hash):
            otp.attempts += 1
            otp.save(update_fields=['attempts'])
            error = '验证码不正确，请重新输入'
        else:
            registration = svc.register(link, kind, value)
            otp.consumed_at = now
            otp.code_hash = ''
            otp.save(update_fields=['consumed_at', 'code_hash'])
    # Raise only after failed-attempt counters have committed.
    if error:
        raise ValidationError(error)
    return registration
