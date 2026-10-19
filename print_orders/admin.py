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
