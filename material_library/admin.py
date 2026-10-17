from django.contrib import admin
from .models import MaterialLibrary, Material, ResourceBlob

@admin.register(MaterialLibrary)
class LibraryAdmin(admin.ModelAdmin):
    list_display = ['title','template','library_type','active','favorite_count']
    list_filter = ['library_type','active','template__series']
    search_fields = ['title','template__title']
    readonly_fields = ['current']
    def favorite_count(self,obj): return obj.favorites.count()

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['source_identity','material_type','active']
    list_filter = ['material_type','active']
    search_fields = ['source_identity']

@admin.register(ResourceBlob)
class BlobAdmin(admin.ModelAdmin):
    list_display = ['sha256','byte_size','width','height']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
