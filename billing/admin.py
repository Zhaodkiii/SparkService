from django.contrib import admin
from .models import BillingIdentity,RechargeProduct,ContentOffer,ContentPolicyRevision,WalletSnapshot,WalletOperation,RedemptionOrder,ContentOwnership,WalletLedgerEntry,CurrencyEvent,ReconciliationCase,BillingAudit

class AuditAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

for model in [BillingIdentity,RechargeProduct,ContentOffer,ContentPolicyRevision,WalletSnapshot,WalletOperation,RedemptionOrder,ContentOwnership,WalletLedgerEntry,CurrencyEvent,ReconciliationCase,BillingAudit]:
    admin.site.register(model,AuditAdmin)
