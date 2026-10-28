"""Explicit free policy for legacy test fixtures (test settings skip data migrations)."""
from .models import ContentOffer,ContentPolicyRevision

def legacy_free(kind,target):
    offer,created=ContentOffer.objects.get_or_create(target_kind=kind,target_id=target.pk,defaults={'title':target.title,'state':'active'})
    if created:
        policy=ContentPolicyRevision.objects.create(offer=offer,revision=1,access_mode='free',terms_version='legacy-test')
        offer.current_policy_revision=policy;offer.save()
    return offer
