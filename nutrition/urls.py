from django.urls import path

from nutrition.views import (
    NutritionAppleHealthEnergyBurnImportAPIView,
    NutritionAppleHealthIntakeImportAPIView,
    NutritionDashboardAPIView,
    NutritionDefaultsPreviewAPIView,
    NutritionEnergyBurnAppleHealthIdAPIView,
    NutritionEnergyBurnDetailAPIView,
    NutritionEnergyBurnListCreateAPIView,
    NutritionFavoriteAPIView,
    NutritionFoodItemCreateAPIView,
    NutritionHealthAPIView,
    NutritionIntakeAppleHealthIdAPIView,
    NutritionMealRecordDetailAPIView,
    NutritionMealRecordListCreateAPIView,
    NutritionRecipeCreateAPIView,
    NutritionSearchAPIView,
)

urlpatterns = [
    # GET — 模块健康检查，返回 nutrition 服务状态及预置食物数量
    path("health/", NutritionHealthAPIView.as_view(), name="nutrition-health"),
    # GET — 预览成员默认营养目标与餐次宏量分配（goal、meal_targets）
    path("defaults/", NutritionDefaultsPreviewAPIView.as_view(), name="nutrition-defaults"),
    # GET — 获取指定成员、指定日期的营养看板汇总（摄入、消耗、目标进度等）
    path("dashboard/", NutritionDashboardAPIView.as_view(), name="nutrition-dashboard"),
    # GET — 查询餐食记录（单日按 meal_type 筛选，或 date_from/date_to 历史范围）；POST — 创建餐食记录
    path("meal-records/", NutritionMealRecordListCreateAPIView.as_view(), name="nutrition-meal-records"),
    # PATCH — 更新餐食记录；DELETE — 软删除餐食记录
    path("meal-records/<int:record_id>/", NutritionMealRecordDetailAPIView.as_view(), name="nutrition-meal-record-detail"),
    # GET — 搜索食物/菜谱（支持文本、条码等模式，可筛选收藏与自建）
    path("search/", NutritionSearchAPIView.as_view(), name="nutrition-search"),
    # POST — 添加收藏；DELETE — 按 target_type + target_id 取消收藏
    path("favorites/", NutritionFavoriteAPIView.as_view(), name="nutrition-favorites"),
    # POST — 创建用户自定义食物条目及对应标准营养摄入
    path("food-items/", NutritionFoodItemCreateAPIView.as_view(), name="nutrition-food-items"),
    # POST — 创建用户自定义菜谱及汇总后的标准营养摄入
    path("recipes/", NutritionRecipeCreateAPIView.as_view(), name="nutrition-recipes"),
    # GET — 查询指定日期的能量消耗记录；POST — 创建能量消耗记录
    path("energy-burn-records/", NutritionEnergyBurnListCreateAPIView.as_view(), name="nutrition-energy-burn-records"),
    # PATCH — 更新能量消耗记录；DELETE — 软删除能量消耗记录
    path("energy-burn-records/<int:record_id>/", NutritionEnergyBurnDetailAPIView.as_view(), name="nutrition-energy-burn-detail"),
    # POST — 批量导入 Apple Health 营养摄入样本，自动去重并创建关联摄入记录
    path("apple-health/intake-imports/", NutritionAppleHealthIntakeImportAPIView.as_view(), name="nutrition-apple-health-intake-imports"),
    # POST — 批量导入 Apple Health 能量消耗样本，自动去重并创建关联消耗记录
    path("apple-health/energy-burn-imports/", NutritionAppleHealthEnergyBurnImportAPIView.as_view(), name="nutrition-apple-health-energy-burn-imports"),
    # POST — 为指定摄入记录回写 Apple Health 样本 ID，用于双向同步与去重
    path("intakes/<int:intake_id>/apple-health-id/", NutritionIntakeAppleHealthIdAPIView.as_view(), name="nutrition-intake-apple-health-id"),
    # POST — 为指定能量消耗记录回写 Apple Health 样本 ID，用于双向同步与去重
    path("energy-burn-records/<int:record_id>/apple-health-id/", NutritionEnergyBurnAppleHealthIdAPIView.as_view(), name="nutrition-energy-burn-apple-health-id"),
]
