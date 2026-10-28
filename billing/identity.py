import hashlib
from pathlib import Path
from django.core.exceptions import ValidationError as DjangoValidationError
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import APIException
from .models import BillingIdentity, WalletGate, WalletSnapshot, WalletSession

class BillingError(APIException):
    status_code = 409
    def __init__(self, code, message=None, status=409):
        self.status_code = status
        super().__init__({'code':code,'message':message or code})

def verify_environment(jws):
    if not isinstance(jws,str) or not 1 <= len(jws) <= 30000:
        raise BillingError('ENVIRONMENT_UNVERIFIED','无法验证商店环境')
    from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException
    from appstoreserverlibrary.models.Environment import Environment
    roots = [p.read_bytes() for p in Path(settings.BILLING_APPLE_ROOTS_DIR).glob('*.cer')]
    if not roots: raise BillingError('ENVIRONMENT_UNVERIFIED','商店验证证书尚未配置',503)
    for environment, domain in [(Environment.PRODUCTION,'production'),(Environment.SANDBOX,'sandbox')]:
        try:
            verifier = SignedDataVerifier(roots, True, environment, settings.BILLING_BUNDLE_ID,settings.BILLING_APPLE_APP_ID)
            verifier.verify_and_decode_app_transaction(jws)
            return domain
        except VerificationException:
            continue
    raise BillingError('ENVIRONMENT_UNVERIFIED','商店凭证无效，请从 App Store 或 TestFlight 安装')

def bootstrap(user,jws):
    if not user.social_identities.exclude(provider='device').exists():
        raise BillingError('FORMAL_ACCOUNT_REQUIRED','请先绑定正式账号',403)
    domain = verify_environment(jws)
    identity,_ = BillingIdentity.objects.get_or_create(account=user,rc_project_id=settings.REVENUECAT_PROJECT_ID,wallet_domain=domain)
    if identity.state != 'active': raise BillingError('WALLET_UNDER_REVIEW','钱包正在核验')
    WalletGate.objects.get_or_create(identity=identity)
    WalletSnapshot.objects.get_or_create(identity=identity)
    session = WalletSession.objects.create(identity=identity,expires_at=timezone.now()+timedelta(hours=12),proof_digest=hashlib.sha256(jws.encode()).hexdigest())
    return session

def identity_for(request):
    key = request.headers.get('X-Billing-Session','')
    try:
        session = WalletSession.objects.select_related('identity').get(pk=key,identity__account=request.user,identity__rc_project_id=settings.REVENUECAT_PROJECT_ID,expires_at__gt=timezone.now())
    except (WalletSession.DoesNotExist,ValueError,TypeError,DjangoValidationError):
        raise BillingError('WALLET_IDENTITY_PENDING','请刷新钱包身份',403)
    if session.identity.state != 'active': raise BillingError('WALLET_UNDER_REVIEW','钱包正在核验')
    return session.identity
