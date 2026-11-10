from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'active', 'proof_approved', 'revision']
    readonly_fields = [field.name for field in Product._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False
    # 所有编辑经业务管理页执行相同的打样、开放与并发检查。


from .models import PrintCoupon


@admin.register(PrintCoupon)
class PrintCouponAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'product', 'percent', 'expires_at', 'order']
    raw_id_fields = ['owner', 'product']
    readonly_fields = ['order', 'issued_at']
    search_fields = ['grant_key', 'name']

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from django.db import transaction
from .models import PrintCampaign, PrintEnrollment
from .campaigns import award


@admin.register(PrintCampaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['title','source','active','starts_at','ends_at','quota']

    def get_readonly_fields(self, request, obj=None):
        if obj and PrintEnrollment.objects.filter(plan=obj).exists():
            return [f.name for f in PrintCampaign._meta.fields if f.name!='active']
        return []


@admin.register(PrintEnrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['owner','plan','book_id','reported_pages','approved_pages','coupon']
    readonly_fields = [f.name for f in PrintEnrollment._meta.fields]
    actions = ['approve_half','approve_free']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def approve(self, queryset, threshold):
        with transaction.atomic():
            for entry in queryset.exclude(coupon__percent=100).filter(plan__source='pages',withdrawn_at__isnull=True,reported_pages__gte=threshold).select_for_update():
                award(entry,100 if threshold==40 else 50)
                entry.approved_pages=max(entry.approved_pages,threshold)
                entry.save(update_fields=['approved_pages'])

    @admin.action(description='确认已核验 20 页，发半价券')
    def approve_half(self, request, queryset):
        self.approve(queryset,20)

    @admin.action(description='确认已核验 40 页，发免费券')
    def approve_free(self, request, queryset):
        self.approve(queryset,40)
