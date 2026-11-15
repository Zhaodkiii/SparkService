from django.contrib import admin
from .models import BillingIdentity,RechargeProduct,ContentOffer,ContentPolicyRevision,WalletSnapshot,WalletOperation,RedemptionOrder,ContentOwnership,WalletLedgerEntry,CurrencyEvent,ReconciliationCase,BillingAudit,WebhookDelivery

class AuditAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

for model in [BillingIdentity,RechargeProduct,ContentOffer,ContentPolicyRevision,WalletSnapshot,WalletOperation,RedemptionOrder,ContentOwnership,WalletLedgerEntry,CurrencyEvent,ReconciliationCase,BillingAudit]:
    admin.site.register(model,AuditAdmin)

@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(AuditAdmin):
    list_display = ('event', 'attempts', 'last_status', 'next_attempt_at', 'delivered_at')
    list_filter = ('last_status',)
    search_fields = ('event__event_id',)
