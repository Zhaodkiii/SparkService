from django.conf import settings

RUNTIME_FLAGS = {'DIAMOND_REDEMPTION_ENABLED':'diamond_redemption_enabled', 'MEMBERSHIP_SALES_ENABLED':'membership_sales_enabled'}

def sales_enabled(feature):
    if feature not in RUNTIME_FLAGS:return bool(getattr(settings,feature,False))
    from .models import SalesControl
    control=SalesControl.objects.filter(pk=1).first()
    return bool(getattr(control,RUNTIME_FLAGS[feature])) if control else bool(getattr(settings,feature,False))

def enabled(feature,identity):
    """Sandbox override requires the environment verified from Apple's signed proof."""
    return bool(sales_enabled(feature) or (identity.wallet_domain=='sandbox' and settings.BILLING_SANDBOX_SALES_ENABLED))

def client_flags(identity):
    return {name.lower():enabled(name,identity) for name in ('DIAMOND_RECHARGE_ENABLED','DIAMOND_REDEMPTION_ENABLED','DIAMOND_CUSTOMIZATION_ENABLED','MEMBERSHIP_SALES_ENABLED')}
