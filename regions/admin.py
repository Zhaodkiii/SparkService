from django.contrib import admin, messages
from .models import RegionDataset, RegionState, RegionSyncRun, RegionPublication
from .services import publish
from .tasks import check_regions

@admin.register(RegionDataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display=('version','status','fetched_at','published_at','counts')
    readonly_fields=tuple(f.name for f in RegionDataset._meta.fields if f.name != "artifact")
    exclude=('artifact',)
    actions=['publish_selected']
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    @admin.action(description='审核发布所选版本（选择旧版本可回滚）')
    def publish_selected(self,request,queryset):
        if queryset.count()!=1:
            self.message_user(request,'请选择一个版本并核验差异',messages.ERROR);return
        try:
            publish(queryset.first().pk,str(request.user.pk),'Django admin reviewed publication/rollback')
            self.message_user(request,'已发布地区版本')
        except ValueError as e: self.message_user(request,str(e),messages.ERROR)

class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self,request,obj=None): return tuple(f.name for f in self.model._meta.fields)
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False

@admin.register(RegionState)
class StateAdmin(ReadOnlyAdmin):
    actions=['schedule_sync']
    @admin.action(description='立即检查高德地区更新（遵守任务锁和每日预算）')
    def schedule_sync(self,request,queryset):
        check_regions.delay(force=True)
        self.message_user(request,'已提交同步检查；新数据进入候选版本，核验后再发布')

admin.site.register(RegionSyncRun,ReadOnlyAdmin)
admin.site.register(RegionPublication,ReadOnlyAdmin)
