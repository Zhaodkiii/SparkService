"""Invitation records share the public experience app, never the billing wallet."""
import uuid
from django.conf import settings
from django.db import models

class InvitationCampaign(models.Model):
    title = models.CharField(max_length=100)
    active = models.BooleanField(default=False)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    download_url = models.URLField()
    attribution_days = models.PositiveSmallIntegerField(default=7)
    card_days = models.PositiveSmallIntegerField(default=30)
    cards_per_invite = models.PositiveSmallIntegerField(default=0)
    card_invite_limit = models.PositiveSmallIntegerField(default=10)
    participant_limit = models.PositiveIntegerField(default=100)
    automatic = models.BooleanField(default=False)
    print_campaign = models.ForeignKey('print_orders.PrintCampaign', on_delete=models.PROTECT)
    rules = models.TextField()
    print_snapshot = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

class InvitationLink(models.Model):
    token = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(InvitationCampaign, on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['campaign','owner'],name='invitation_participant_once')]

class InvitationRegistration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    link = models.ForeignKey(InvitationLink, on_delete=models.PROTECT)
    contact_kind = models.CharField(max_length=10)
    contact_hash = models.CharField(max_length=64, db_index=True)
    # No plaintext contact persisted. App authentication proves control of contact.
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['link','contact_kind','contact_hash'],name='invitation_registration_once')]

class InvitationConversion(models.Model):
    registration = models.OneToOneField(InvitationRegistration,on_delete=models.PROTECT)
    invitee = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='invitation_conversion')
    confirmed_at = models.DateTimeField(auto_now_add=True)

class InvitationIdentityEvent(models.Model):
    identity = models.ForeignKey('accounts.SocialIdentity',on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)

class InvitationReward(models.Model):
    link = models.ForeignKey(InvitationLink,on_delete=models.PROTECT)
    key = models.CharField(max_length=160,unique=True)
    kind = models.CharField(max_length=16)
    threshold = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField(default=1)
    issued_at = models.DateTimeField(null=True)
    notified_at = models.DateTimeField(null=True)
    coupon = models.OneToOneField('print_orders.PrintCoupon',on_delete=models.PROTECT,null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class InvitationAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True)
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=160)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
