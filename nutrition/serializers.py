"""饮食营养 API 序列化器。"""

from rest_framework import serializers

from nutrition.models import NutritionEnergyBurnRecord, NutritionMealRecord


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
