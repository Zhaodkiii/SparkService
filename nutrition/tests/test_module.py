from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import Member
from nutrition.constants import DEFAULT_DAILY_GOAL, NUTRITION_BUSINESS_TYPE_FOOD_ITEM
from nutrition.models import NutritionFoodItem, NutritionIntake, NutritionMealRecord
from nutrition.services.goal_service import resolve_goal_payload, resolve_meal_macro_targets
from nutrition.services.seed_data import SYSTEM_FOODS, seed_system_foods

User = get_user_model()


class NutritionModuleImportTests(TestCase):
    def test_models_importable(self):
        self.assertEqual(NutritionMealRecord.MealType.BREAKFAST, "breakfast")
        self.assertEqual(len(SYSTEM_FOODS), 5)


class NutritionHealthAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="nutrition_tester",
            email="nutrition@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)

    def test_health_endpoint_returns_module_status(self):
        response = self.client.get("/api/v1/nutrition/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["code"], 0)
        self.assertEqual(body["data"]["module"], "nutrition")
        self.assertEqual(body["data"]["status"], "ok")
        self.assertTrue(body["data"]["request_id"])


class NutritionSeedDataTests(TestCase):
    def test_seed_system_foods_creates_verified_items_and_intakes(self):
        seed_system_foods()
        foods = NutritionFoodItem.objects.filter(user__isnull=True, source="system", is_verified=True)
        self.assertEqual(foods.count(), 5)

        coffee = foods.get(name="Coffee")
        intakes = NutritionIntake.objects.filter(
            business_type=NUTRITION_BUSINESS_TYPE_FOOD_ITEM,
            business_id=coffee.id,
        )
        self.assertEqual(intakes.count(), 4)
        energy = intakes.get(nutrient_type="energy_kcal")
        self.assertEqual(energy.value, Decimal("2"))

        apple = foods.get(name="Apple")
        self.assertEqual(apple.barcode, "6926104997449")


class NutritionGoalServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="nutrition_goal_tester",
            email="goal@example.com",
            password="test123456",
        )
        self.member = Member.objects.create(user=self.user, name="Self", is_primary=True)

    def test_default_goal_payload_matches_design_doc(self):
        payload = resolve_goal_payload(self.user, self.member.id)
        self.assertEqual(payload["energy_kcal"], float(DEFAULT_DAILY_GOAL["energy_kcal"]))
        self.assertEqual(payload["protein_g"], float(DEFAULT_DAILY_GOAL["protein_g"]))

    def test_default_meal_targets_use_distribution(self):
        meal_targets = resolve_meal_macro_targets(self.user, self.member.id)
        self.assertEqual(meal_targets["breakfast"]["target_energy_kcal"], 598.5)
