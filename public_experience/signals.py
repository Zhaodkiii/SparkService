from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import LoginAudit
from .models import InvitationIdentityEvent


def record_identity_events(user):
    for identity in user.social_identities.filter(provider__in=['phone','email']):
        InvitationIdentityEvent.objects.create(identity=identity)


@receiver(post_save,sender=LoginAudit)
def login_verified(sender,instance,created,**kwargs):
    # Only native authenticated sessions; public Web registration creates no login.
    if created and instance.outcome=='success' and instance.user_id and instance.device_id and instance.bundle_id == settings.BILLING_BUNDLE_ID:
        record_identity_events(instance.user)
