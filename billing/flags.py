from django.conf import settings

def enabled(feature,identity):
    """Sandbox override requires the environment verified from Apple's signed proof."""
    return bool(getattr(settings,feature,False) or (identity.wallet_domain=='sandbox' and settings.BILLING_SANDBOX_SALES_ENABLED))

def client_flags(identity):
    return {name.lower():enabled(name,identity) for name in ('DIAMOND_RECHARGE_ENABLED','DIAMOND_REDEMPTION_ENABLED','DIAMOND_CUSTOMIZATION_ENABLED','MEMBERSHIP_SALES_ENABLED')}
