from datetime import timedelta
from unittest.mock import patch
import re
import uuid
from django.core import mail
from django.core.cache import cache
from django.test import override_settings, TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError, Throttled
from rest_framework.test import APIClient
from accounts.infrastructure.sms_provider import SMSProviderResult
from . import tests_invitations as fixtures
from .models import InvitationOTP, InvitationRegistration, InvitationConversion
from .invitation_otp import request_code, verify_and_register


class InvitationOTPTests(TestCase):
    def setUp(self):
        fixtures.InvitationFlowTests.setUp(self)
        cache.clear()

    def email_code(self, address='new@example.com', link=None):
        result = request_code(link or self.link, 'email', address)
        code = re.search(r'\b[0-9]{6}\b', mail.outbox[-1].body).group()
        return result['challenge_id'], code

    def test_email_registration_requires_proof_and_is_one_time(self):
        challenge, code = self.email_code()
        self.assertFalse(InvitationRegistration.objects.exists())
        result = APIClient().post(f'/api/public/v1/invitations/{self.link.pk}/', dict(
            contact_kind='email', contact='NEW@example.com', challenge_id=challenge, code=code, consent=True), format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['data']['status'], 'awaiting_app')
        self.assertFalse(InvitationConversion.objects.exists())
        self.assertNotIn('new@example.com', str(list(InvitationOTP.objects.values())))
        self.assertNotIn('new@example.com', str(list(InvitationRegistration.objects.values())))
        with self.assertRaises(ValidationError):
            verify_and_register(self.link, 'email', 'new@example.com', challenge, code)

    def test_wrong_code_attempts_are_committed(self):
        challenge, code = self.email_code()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            with self.assertRaises(ValidationError):
                verify_and_register(self.link, 'email', 'new@example.com', challenge, wrong)
        self.assertEqual(InvitationOTP.objects.get().attempts, 5)
        with self.assertRaises(ValidationError):
            verify_and_register(self.link, 'email', 'new@example.com', challenge, code)
        self.assertFalse(InvitationRegistration.objects.exists())

    def test_contact_challenge_expiry_and_link_binding(self):
        challenge, code = self.email_code()
        for address, identifier in [('other@example.com', challenge), ('new@example.com', uuid.uuid4())]:
            with self.assertRaises(ValidationError):
                verify_and_register(self.link, 'email', address, identifier, code)
        from .models import InvitationLink
        other = type(self.owner).objects.create_user('another-inviter')
        link = InvitationLink.objects.create(owner=other, campaign=self.c)
        with self.assertRaises(ValidationError):
            verify_and_register(link, 'email', 'new@example.com', challenge, code)
        InvitationOTP.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            verify_and_register(self.link, 'email', 'new@example.com', challenge, code)

    def test_resend_and_daily_budget(self):
        old, code = self.email_code()
        with self.assertRaises(Throttled): self.email_code()
        InvitationOTP.objects.update(sent_at=timezone.now()-timedelta(seconds=61))
        new, new_code = self.email_code()
        with self.assertRaises(ValidationError):
            verify_and_register(self.link, 'email', 'new@example.com', old, code)
        InvitationOTP.objects.update(sent_at=timezone.now()-timedelta(seconds=61), send_count=10)
        with self.assertRaises(Throttled): self.email_code()
        verify_and_register(self.link, 'email', 'new@example.com', new, new_code)

    @patch('public_experience.invitation_otp.AliyunSMSProvider.otp_readiness_error', return_value='')
    @patch('public_experience.invitation_otp.AliyunSMSProvider.send_login_code', return_value=SMSProviderResult(True, False, ''))
    def test_phone_uses_existing_provider(self, sender, ready):
        result = request_code(self.link, 'phone', '13800138000')
        values = sender.call_args.kwargs
        self.assertEqual(values['phone_number'], '+8613800138000')
        self.assertRegex(values['code'], r'^[0-9]{6}$')
        verify_and_register(self.link, 'phone', '+8613800138000', result['challenge_id'], values['code'])
        self.assertEqual(InvitationRegistration.objects.count(), 1)

    @patch('public_experience.invitation_otp.send_mail', side_effect=RuntimeError('delivery error'))
    def test_failed_delivery_cannot_verify(self, sender):
        with self.assertRaises(ValidationError): self.email_code()
        self.assertEqual(InvitationOTP.objects.get().code_hash, '')
        self.assertFalse(InvitationRegistration.objects.exists())
        with self.assertRaises(Throttled): self.email_code()

    def test_unavailable_campaign_and_consent(self):
        client = APIClient()
        endpoint = f'/api/public/v1/invitations/{self.link.pk}/code/'
        for consent in (None, False):
            body = dict(contact_kind='email', contact='new@example.com')
            if consent is not None: body['consent'] = consent
            self.assertEqual(client.post(endpoint, body, format='json').status_code, 400)
        self.c.active=False; self.c.save()
        self.assertEqual(client.post(endpoint, dict(contact_kind='email', contact='new@example.com', consent=True), format='json').status_code, 400)
        self.assertFalse(InvitationOTP.objects.exists())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_console_backend_is_not_delivery(self):
        with self.assertRaises(ValidationError): self.email_code()
        self.assertEqual(InvitationOTP.objects.get().code_hash, '')
