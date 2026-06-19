"""饮食营养 API 序列化器。"""

from decimal import Decimal

from rest_framework import serializers

from nutrition.models import NutritionEnergyBurnRecord, NutritionGoal, NutritionMealRecord


MAX_WEEKLY_WEIGHT_DELTA_KG = Decimal("1.00")
MAX_DAILY_ENERGY_TARGET_KCAL = Decimal("10000.00")
MAX_MACRO_TARGET_G = Decimal("2000.00")
WEIGHT_STABLE_GOALS = {
    NutritionGoal.GoalType.MAINTAIN,
    NutritionGoal.GoalType.CONTROL_SUGAR,
    NutritionGoal.GoalType.CONTROL_SALT,
    NutritionGoal.GoalType.CONTROL_FAT,
}
WEIGHT_LOSS_GOALS = {NutritionGoal.GoalType.LOSE_WEIGHT}
WEIGHT_GAIN_GOALS = {
    NutritionGoal.GoalType.GAIN_WEIGHT,
    NutritionGoal.GoalType.GAIN_MUSCLE,
    NutritionGoal.GoalType.BUILD_MUSCLE,
}


def _validate_weekly_weight_delta(attrs):
    goal_type = attrs.get("goal_type")
    weekly_delta = attrs.get("weekly_weight_delta_kg")
    if weekly_delta is None:
        return

    errors = {}
    if abs(weekly_delta) > MAX_WEEKLY_WEIGHT_DELTA_KG:
        errors["weekly_weight_delta_kg"] = "must_be_between_minus_1_and_1"
    elif goal_type in WEIGHT_STABLE_GOALS and weekly_delta != 0:
        errors["weekly_weight_delta_kg"] = "must_be_zero_for_goal_type"
    elif goal_type in WEIGHT_LOSS_GOALS and weekly_delta > 0:
        errors["weekly_weight_delta_kg"] = "must_not_be_positive_for_lose_weight"
    elif goal_type in WEIGHT_GAIN_GOALS and weekly_delta < 0:
        errors["weekly_weight_delta_kg"] = "must_not_be_negative_for_gain_goal"

    if errors:
        raise serializers.ValidationError(errors)


def _validate_goal_target_bounds(attrs):
    errors = {}
    daily_energy = attrs.get("daily_energy_target_kcal")
    if daily_energy is not None:
        if daily_energy < 0:
            errors["daily_energy_target_kcal"] = "must_not_be_negative"
        elif daily_energy > MAX_DAILY_ENERGY_TARGET_KCAL:
            errors["daily_energy_target_kcal"] = "must_not_exceed_10000"

    for field in ("carbohydrate_target_g", "protein_target_g", "fat_target_g"):
        value = attrs.get(field)
        if value is not None:
            if value < 0:
                errors[field] = "must_not_be_negative"
            elif value > MAX_MACRO_TARGET_G:
                errors[field] = "must_not_exceed_2000"

    if errors:
        raise serializers.ValidationError(errors)


class ManualIntakeSerializer(serializers.Serializer):
    nutrient_type = serializers.CharField(max_length=32)
    value = serializers.DecimalField(max_digits=10, decimal_places=2)
    unit = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    source = serializers.CharField(max_length=32, required=False, allow_blank=True, default="manual")


class MealFoodInputSerializer(serializers.Serializer):
    food_item_id = serializers.IntegerField()
    serving_ratio = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, default=1)
    serving_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    serving_unit = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    serving_description = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class RecipeInputSerializer(serializers.Serializer):
    recipe_id = serializers.IntegerField()
    serving_ratio = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, default=1)
    serving_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    serving_unit = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    serving_description = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class MealRecordCreateSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    meal_type = serializers.ChoiceField(choices=NutritionMealRecord.MealType.values)
    consumed_at = serializers.DateTimeField()
    source = serializers.ChoiceField(choices=NutritionMealRecord.Source.values, required=False, default=NutritionMealRecord.Source.MANUAL)
    source_text = serializers.CharField(required=False, allow_blank=True, default="")
    title = serializers.CharField(required=False, allow_blank=True, default="")
    recognition_id = serializers.CharField(required=False, allow_blank=True, default="")
    file_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    meal_foods = MealFoodInputSerializer(many=True, required=False, default=list)
    recipes = RecipeInputSerializer(many=True, required=False, default=list)
    manual_intakes = ManualIntakeSerializer(many=True, required=False, default=list)


class MealRecordUpdateSerializer(serializers.Serializer):
    meal_type = serializers.ChoiceField(choices=NutritionMealRecord.MealType.values, required=False)
    consumed_at = serializers.DateTimeField(required=False)
    source = serializers.ChoiceField(choices=NutritionMealRecord.Source.values, required=False)
    source_text = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    file_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    meal_foods = MealFoodInputSerializer(many=True, required=False)
    recipes = RecipeInputSerializer(many=True, required=False)
    manual_intakes = ManualIntakeSerializer(many=True, required=False)


class FavoriteSerializer(serializers.Serializer):
    target_type = serializers.CharField(max_length=64)
    target_id = serializers.IntegerField()


class FoodItemCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    localized_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    brand_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    barcode = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    category = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    serving_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    serving_unit = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    serving_description = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    weight_grams = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    intakes = ManualIntakeSerializer(many=True, required=False, default=list)


class RecipeFoodInputSerializer(serializers.Serializer):
    food_item_id = serializers.IntegerField()
    serving_ratio = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, default=1)
    serving_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    serving_unit = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    serving_description = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class RecipeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    localized_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    category = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    serving_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    serving_unit = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    serving_description = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    foods = RecipeFoodInputSerializer(many=True, required=False, default=list)


class EnergyBurnCreateSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    burned_at = serializers.DateTimeField()
    energy_kcal = serializers.DecimalField(max_digits=10, decimal_places=2)
    activity_type = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    duration_seconds = serializers.IntegerField(required=False, allow_null=True)
    source = serializers.ChoiceField(choices=NutritionEnergyBurnRecord.Source.values, required=False, default=NutritionEnergyBurnRecord.Source.MANUAL)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class EnergyBurnUpdateSerializer(serializers.Serializer):
    burned_at = serializers.DateTimeField(required=False)
    energy_kcal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    activity_type = serializers.CharField(max_length=64, required=False, allow_blank=True)
    duration_seconds = serializers.IntegerField(required=False, allow_null=True)
    source = serializers.CharField(max_length=32, required=False)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AppleHealthIntakeSampleSerializer(serializers.Serializer):
    apple_health_id = serializers.CharField(max_length=128)
    occurred_at = serializers.DateTimeField()
    source_bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    source_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    intakes = ManualIntakeSerializer(many=True, required=False, default=list)


class AppleHealthIntakeImportSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    samples = AppleHealthIntakeSampleSerializer(many=True)


class AppleHealthEnergyBurnSampleSerializer(serializers.Serializer):
    apple_health_id = serializers.CharField(max_length=128)
    burned_at = serializers.DateTimeField()
    energy_kcal = serializers.DecimalField(max_digits=10, decimal_places=2)
    activity_type = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    source = serializers.CharField(max_length=32, required=False, allow_blank=True, default="apple_health_import")


class AppleHealthEnergyBurnImportSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    samples = AppleHealthEnergyBurnSampleSerializer(many=True)


class AppleHealthIdSerializer(serializers.Serializer):
    apple_health_id = serializers.CharField(max_length=128)


class NutritionGoalSerializer(serializers.ModelSerializer):
    member_id = serializers.IntegerField(source="member.id", read_only=True)

    class Meta:
        model = NutritionGoal
        fields = (
            "id",
            "user",
            "member",
            "member_id",
            "goal_type",
            "height_cm",
            "current_weight_kg",
            "target_weight_kg",
            "biological_sex",
            "age_years",
            "activity_level",
            "weekly_weight_delta_kg",
            "bmr_kcal",
            "tdee_kcal",
            "energy_delta_kcal",
            "calculation_formula",
            "calculation_version",
            "calculation_inputs",
            "is_energy_target_custom",
            "weekend_energy_target_kcal",
            "is_weekend_energy_enabled",
            "step_target",
            "daily_energy_target_kcal",
            "carbohydrate_target_g",
            "protein_target_g",
            "fat_target_g",
            "meal_distribution",
            "effective_from",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class NutritionGoalUpsertSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    goal_type = serializers.ChoiceField(choices=NutritionGoal.GoalType.choices)
    height_cm = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    current_weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    target_weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    biological_sex = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    age_years = serializers.IntegerField(required=False, allow_null=True)
    activity_level = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    weekly_weight_delta_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    bmr_kcal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    tdee_kcal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    energy_delta_kcal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    calculation_formula = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    calculation_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    calculation_inputs = serializers.JSONField(required=False, default=dict)
    is_energy_target_custom = serializers.BooleanField(required=False, default=False)
    weekend_energy_target_kcal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    is_weekend_energy_enabled = serializers.BooleanField(required=False, default=False)
    step_target = serializers.IntegerField(required=False, allow_null=True)
    daily_energy_target_kcal = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    carbohydrate_target_g = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    protein_target_g = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    fat_target_g = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    meal_distribution = serializers.JSONField(required=False, default=dict)
    effective_from = serializers.DateField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        _validate_weekly_weight_delta(attrs)
        _validate_goal_target_bounds(attrs)
        return attrs


class NutritionGoalCalculationSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    goal_type = serializers.ChoiceField(choices=NutritionGoal.GoalType.choices, required=False, default=NutritionGoal.GoalType.MAINTAIN)
    activity_level = serializers.CharField(max_length=32, required=False, allow_blank=True, default="low")
    current_weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    height_cm = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    biological_sex = serializers.CharField(max_length=16, required=False, allow_blank=True, allow_null=True)
    age_years = serializers.IntegerField(required=False, allow_null=True)
    weekly_weight_delta_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    target_weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)

    def validate(self, attrs):
        _validate_weekly_weight_delta(attrs)
        return attrs
