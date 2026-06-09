from django.contrib import admin

from nutrition.models import (
    NutritionAppleHealthIntakeImport,
    NutritionEnergyBurnRecord,
    NutritionFoodFavorite,
    NutritionFoodItem,
    NutritionGoal,
    NutritionIntake,
    NutritionMealFood,
    NutritionMealRecord,
    NutritionRecipe,
    NutritionRecipeFood,
)

admin.site.register(NutritionFoodItem)
admin.site.register(NutritionMealRecord)
admin.site.register(NutritionMealFood)
admin.site.register(NutritionIntake)
admin.site.register(NutritionRecipe)
admin.site.register(NutritionRecipeFood)
admin.site.register(NutritionFoodFavorite)
admin.site.register(NutritionEnergyBurnRecord)
admin.site.register(NutritionAppleHealthIntakeImport)
admin.site.register(NutritionGoal)
