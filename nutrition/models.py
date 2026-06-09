from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from medical.models import SoftDeleteManager


class NutritionBaseModel(models.Model):
    """饮食营养成员级业务模型基类。"""

    user = models.ForeignKey(User, related_name="%(class)s_records", on_delete=models.CASCADE, db_index=True, db_comment="当前登录账号 ID，用于权限边界、数据归属和跨成员查询隔离")
    member = models.ForeignKey("medical.Member", related_name="%(class)s_records", on_delete=models.CASCADE, db_index=True, db_comment="饮食营养数据归属成员 ID，与账号用户不同，用于家庭成员饮食记录归属")
    is_deleted = models.BooleanField(default=False, db_index=True, db_comment="软删除标记；true 表示业务已删除但数据库保留记录")
    deleted_at = models.DateTimeField(null=True, blank=True, db_comment="软删除时间；未删除时为空")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="记录创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="记录最后更新时间，用于增量同步、列表排序和缓存失效判断")

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class NutritionMealRecord(NutritionBaseModel):
    """饮食记录主表：一次餐次内的一组食物聚合根。"""

    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "breakfast"
        LUNCH = "lunch", "lunch"
        DINNER = "dinner", "dinner"
        SNACK = "snack", "snack"

    class Source(models.TextChoices):
        MANUAL = "manual", "manual"
        PHOTO_AI = "photo_ai", "photo_ai"
        TEXT_AI = "text_ai", "text_ai"
        CHAT_AI = "chat_ai", "chat_ai"
        APPLE_HEALTH_IMPORT = "apple_health_import", "apple_health_import"

    meal_type = models.CharField(max_length=16, choices=MealType.choices, db_index=True, db_comment="餐次类型：早餐、午餐、晚餐、小吃")
    consumed_at = models.DateTimeField(db_index=True, db_comment="实际食用时间；由用户选择或创建记录时生成，用于时间线排序")
    local_day = models.DateField(db_index=True, db_comment="用户本地日期；用于日看板、餐次列表和按天聚合")
    title = models.CharField(max_length=128, blank=True, default="", db_comment="饮食记录标题；可为空")
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.MANUAL, db_index=True, db_comment="记录来源：手动、拍照 AI、文本 AI、对话 AI、Apple 健康导入等")
    source_text = models.TextField(blank=True, default="", db_comment="AI 整理时的用户原始输入文本或识别来源摘要")
    is_ai_estimated = models.BooleanField(default=False, db_index=True, db_comment="是否包含 AI 估算结果")
    ai_confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, db_comment="AI 对本餐识别或整理结果的整体置信度，范围 0 到 1")
    user_edited = models.BooleanField(default=False, db_index=True, db_comment="用户是否编辑过 AI 草稿或系统推荐值")
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段；仅承载一期未结构化但需要保留的信息")

    class Meta:
        ordering = ["-consumed_at", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "local_day", "meal_type"]),
            models.Index(fields=["user", "member", "consumed_at"]),
            models.Index(fields=["member", "local_day"]),
        ]

    def __str__(self):
        return f"meal_record:{self.id}:{self.meal_type}:{self.local_day}"


class NutritionIntake(models.Model):
    """营养摄入明细：通过 business_type + business_id 关联不同业务对象。"""

    class NutrientType(models.TextChoices):
        ENERGY = "energy_kcal", "energy_kcal"
        PROTEIN = "protein_g", "protein_g"
        CARBOHYDRATE = "carbohydrate_g", "carbohydrate_g"
        FAT = "fat_g", "fat_g"

    business_type = models.CharField(max_length=64, db_index=True, db_comment="营养归属业务类型，例如 nutrition_meal_record、nutrition_food_item")
    business_id = models.BigIntegerField(db_index=True, db_comment="营养归属业务 ID，与 business_type 一起定位所属对象")
    nutrient_type = models.CharField(max_length=32, choices=NutrientType.choices, db_index=True, db_comment="营养类型，例如热量、蛋白质、碳水化合物、脂肪")
    value = models.DecimalField(max_digits=10, decimal_places=2, db_comment="营养摄入数值")
    unit = models.CharField(max_length=16, db_comment="营养单位，例如 kcal、g、mg")
    source = models.CharField(max_length=32, blank=True, default="", db_comment="摄入值来源，例如 food_item、manual、photo_ai、system")
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, db_comment="AI 估算该营养值的置信度，范围 0 到 1")
    apple_health_id = models.CharField(max_length=128, blank=True, default="", db_index=True, db_comment="Apple 健康写入标识；成功写入 Apple 健康后登记 HealthKit sample UUID")
    extra = models.JSONField(default=dict, blank=True, db_comment="营养摄入扩展字段")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="营养摄入记录创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="营养摄入记录最后更新时间")

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["business_type", "business_id", "nutrient_type"]),
            models.Index(fields=["apple_health_id"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["business_type", "business_id", "nutrient_type"], name="uniq_nutrition_intake_business_nutrient"),
        ]

    def __str__(self):
        return f"intake:{self.business_type}:{self.business_id}:{self.nutrient_type}"


class NutritionFoodItem(models.Model):
    """食物定义：系统预置食物与用户自定义食物。"""

    user = models.ForeignKey(User, related_name="nutrition_food_items", on_delete=models.CASCADE, null=True, blank=True, db_index=True, db_comment="创建该食物的账号 ID；系统预置食物为空")
    name = models.CharField(max_length=128, db_comment="食物标准名称，例如 Coffee")
    localized_name = models.CharField(max_length=128, blank=True, default="", db_comment="食物本地化名称，例如咖啡")
    brand_name = models.CharField(max_length=128, blank=True, default="", db_comment="品牌名称")
    barcode = models.CharField(max_length=64, blank=True, default="", db_index=True, db_comment="包装食品条形码；普通食物为空")
    category = models.CharField(max_length=64, blank=True, default="", db_index=True, db_comment="食物分类，例如主食、水果、饮品")
    serving_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="标准份量数值，例如 1")
    serving_unit = models.CharField(max_length=32, blank=True, default="", db_comment="份量单位，例如 cup、egg、serving")
    serving_description = models.CharField(max_length=128, blank=True, default="", db_comment="份量展示文案，例如 1杯 (237毫升)")
    weight_grams = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="标准份量折算克重，单位 g")
    source = models.CharField(max_length=32, blank=True, default="", db_comment="食物来源，例如 system、user_custom")
    food_database_id = models.CharField(max_length=64, blank=True, default="", db_comment="关联食物库 ID；第一期可为空")
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, db_comment="AI 识别置信度")
    is_verified = models.BooleanField(default=False, db_index=True, db_comment="是否经过系统或运营校验")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否可用")
    sort_weight = models.IntegerField(default=0, db_index=True, db_comment="列表排序权重；用于常用、推荐、系统预置排序")
    extra = models.JSONField(default=dict, blank=True, db_comment="食物项扩展字段")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="食物项创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="食物项最后更新时间")

    class Meta:
        ordering = ["-sort_weight", "name", "id"]
        indexes = [
            models.Index(fields=["is_active", "sort_weight"]),
            models.Index(fields=["name"]),
            models.Index(fields=["localized_name"]),
        ]

    def __str__(self):
        return self.localized_name or self.name


class NutritionFoodFavorite(models.Model):
    """账号维度食物/菜谱收藏。"""

    class TargetType(models.TextChoices):
        FOOD_ITEM = "nutrition_food_item", "nutrition_food_item"
        RECIPE = "nutrition_recipe", "nutrition_recipe"

    user = models.ForeignKey(User, related_name="nutrition_food_favorites", on_delete=models.CASCADE, db_index=True, db_comment="收藏所属账号 ID；收藏是账号维度偏好")
    target_type = models.CharField(max_length=64, choices=TargetType.choices, db_index=True, db_comment="收藏对象类型：食物或菜谱")
    target_id = models.PositiveIntegerField(db_index=True, db_comment="收藏对象 ID")
    is_deleted = models.BooleanField(default=False, db_index=True, db_comment="软删除标记；取消收藏时置为 true")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="收藏创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="收藏最后更新时间")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "target_type", "target_id"]),
        ]

    def __str__(self):
        return f"favorite:{self.user_id}:{self.target_type}:{self.target_id}"


class NutritionMealFood(models.Model):
    """餐次食物关联：某顿饭吃了某个食物及食用比例。"""

    meal_record = models.ForeignKey(NutritionMealRecord, related_name="meal_foods", on_delete=models.CASCADE, db_index=True, db_comment="所属饮食记录 ID")
    food_item = models.ForeignKey(NutritionFoodItem, related_name="meal_foods", on_delete=models.PROTECT, db_index=True, db_comment="本次选择的食物 ID")
    serving_ratio = models.DecimalField(max_digits=8, decimal_places=4, default=1, db_comment="食用比例；全部为 1，1/5 为 0.2")
    serving_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="本次食用份量数值")
    serving_unit = models.CharField(max_length=32, blank=True, default="", db_comment="本次食用份量单位")
    serving_description = models.CharField(max_length=128, blank=True, default="", db_comment="本次食用份量展示文案")
    display_order = models.IntegerField(default=0, db_index=True, db_comment="餐内食物展示顺序")
    extra = models.JSONField(default=dict, blank=True, db_comment="餐次食物关联扩展字段")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="餐次食物关联创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="餐次食物关联最后更新时间")

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"meal_food:{self.meal_record_id}:{self.food_item_id}"


class NutritionRecipe(models.Model):
    """菜谱/组合食物。"""

    user = models.ForeignKey(User, related_name="nutrition_recipes", on_delete=models.CASCADE, null=True, blank=True, db_index=True, db_comment="创建该菜谱的账号 ID；系统预置菜谱为空")
    name = models.CharField(max_length=128, db_index=True, db_comment="菜谱名称")
    localized_name = models.CharField(max_length=128, blank=True, default="", db_index=True, db_comment="菜谱本地化名称")
    category = models.CharField(max_length=64, blank=True, default="", db_index=True, db_comment="菜谱分类")
    serving_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="菜谱标准份量数值")
    serving_unit = models.CharField(max_length=32, blank=True, default="", db_comment="菜谱标准份量单位")
    serving_description = models.CharField(max_length=128, blank=True, default="", db_comment="菜谱标准份量展示文案")
    source = models.CharField(max_length=32, blank=True, default="", db_comment="菜谱来源")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否可用")
    sort_weight = models.IntegerField(default=0, db_index=True, db_comment="列表排序权重")
    extra = models.JSONField(default=dict, blank=True, db_comment="菜谱扩展字段")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="菜谱创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="菜谱最后更新时间")

    class Meta:
        ordering = ["-sort_weight", "name", "id"]

    def __str__(self):
        return self.localized_name or self.name


class NutritionRecipeFood(models.Model):
    """菜谱组成食物。"""

    recipe = models.ForeignKey(NutritionRecipe, related_name="recipe_foods", on_delete=models.CASCADE, db_index=True, db_comment="所属菜谱 ID")
    food_item = models.ForeignKey(NutritionFoodItem, related_name="recipe_foods", on_delete=models.PROTECT, db_index=True, db_comment="菜谱内使用的食物 ID")
    serving_ratio = models.DecimalField(max_digits=8, decimal_places=4, default=1, db_comment="菜谱内该食物相对标准份量的比例")
    serving_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="菜谱内该食物的份量数值")
    serving_unit = models.CharField(max_length=32, blank=True, default="", db_comment="菜谱内该食物的份量单位")
    serving_description = models.CharField(max_length=128, blank=True, default="", db_comment="菜谱内该食物的份量展示文案")
    display_order = models.IntegerField(default=0, db_index=True, db_comment="菜谱内食物展示顺序")
    extra = models.JSONField(default=dict, blank=True, db_comment="菜谱食物关联扩展字段")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="菜谱食物关联创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="菜谱食物关联最后更新时间")

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"recipe_food:{self.recipe_id}:{self.food_item_id}"


class NutritionEnergyBurnRecord(NutritionBaseModel):
    """能量消耗记录：手动录入或 Apple 健康同步。"""

    class Source(models.TextChoices):
        MANUAL = "manual", "manual"
        APPLE_HEALTH_IMPORT = "apple_health_import", "apple_health_import"
        WORKOUT = "workout", "workout"
        AI_ESTIMATED = "ai_estimated", "ai_estimated"

    burned_at = models.DateTimeField(db_index=True, db_comment="能量消耗发生时间")
    local_day = models.DateField(db_index=True, db_comment="用户本地日期；用于日看板和按天聚合")
    energy_kcal = models.DecimalField(max_digits=10, decimal_places=2, db_comment="消耗能量，单位 kcal")
    activity_type = models.CharField(max_length=64, blank=True, default="", db_index=True, db_comment="活动类型，例如 walking、running")
    duration_seconds = models.IntegerField(null=True, blank=True, db_comment="活动持续时长，单位秒")
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.MANUAL, db_index=True, db_comment="记录来源")
    note = models.CharField(max_length=255, blank=True, default="", db_comment="备注")
    apple_health_id = models.CharField(max_length=128, blank=True, default="", db_index=True, db_comment="Apple 健康样本 UUID")
    extra = models.JSONField(default=dict, blank=True, db_comment="能量消耗扩展字段")

    class Meta:
        ordering = ["-burned_at", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "local_day"]),
            models.Index(fields=["apple_health_id"]),
        ]

    def __str__(self):
        return f"energy_burn:{self.id}:{self.energy_kcal}kcal"


class NutritionAppleHealthIntakeImport(NutritionBaseModel):
    """Apple 健康外部营养摄入导入记录。"""

    occurred_at = models.DateTimeField(db_index=True, db_comment="Apple 健康营养摄入样本发生时间")
    local_day = models.DateField(db_index=True, db_comment="用户本地日期")
    source_bundle_id = models.CharField(max_length=128, blank=True, default="", db_comment="Apple 健康样本来源 App bundle id")
    source_name = models.CharField(max_length=128, blank=True, default="", db_comment="Apple 健康样本来源名称")
    apple_health_id = models.CharField(max_length=128, db_index=True, db_comment="HealthKit sample UUID，用于幂等去重")
    extra = models.JSONField(default=dict, blank=True, db_comment="Apple 健康外部营养摄入扩展字段")

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "local_day"]),
            models.Index(fields=["apple_health_id"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["member", "apple_health_id"], name="uniq_nutrition_apple_health_intake_import"),
        ]

    def __str__(self):
        return f"apple_health_intake:{self.apple_health_id}"


class NutritionGoal(models.Model):
    """成员级营养目标配置。"""

    class GoalType(models.TextChoices):
        MAINTAIN = "maintain", "maintain"
        LOSE_WEIGHT = "lose_weight", "lose_weight"
        GAIN_MUSCLE = "gain_muscle", "gain_muscle"
        CUSTOM = "custom", "custom"

    user = models.ForeignKey(User, related_name="nutrition_goals", on_delete=models.CASCADE, db_index=True, db_comment="目标所属账号 ID")
    member = models.ForeignKey("medical.Member", related_name="nutrition_goals", on_delete=models.CASCADE, db_index=True, db_comment="目标归属成员 ID")
    goal_type = models.CharField(max_length=32, choices=GoalType.choices, default=GoalType.MAINTAIN, db_index=True, db_comment="目标类型，例如 maintain、lose_weight")
    daily_energy_target_kcal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="每日热量目标，单位 kcal")
    carbohydrate_target_g = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="每日碳水化合物目标，单位 g")
    protein_target_g = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="每日蛋白质目标，单位 g")
    fat_target_g = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_comment="每日脂肪目标，单位 g")
    meal_distribution = models.JSONField(default=dict, blank=True, db_comment="餐次目标分配比例，例如 breakfast/lunch/dinner/snack")
    effective_from = models.DateField(null=True, blank=True, db_comment="目标生效日期")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否为当前生效目标")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="目标创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="目标最后更新时间")

    class Meta:
        ordering = ["-effective_from", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "is_active"]),
        ]

    def __str__(self):
        return f"goal:member={self.member_id}:type={self.goal_type}"
