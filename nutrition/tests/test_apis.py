from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import Member
from medical.services import member_binding_service as binding_service
from nutrition.models import NutritionFoodItem
from nutrition.services.seed_data import seed_system_foods

User = get_user_model()


class NutritionAPITestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="nutrition_api_tester", email="api@example.com", password="test123456")
        self.client.force_authenticate(self.user)
        self.member = Member.objects.create(user=self.user, name="Self", is_primary=True)
        binding_service.create_owner_binding(user=self.user, member=self.member, relationship="self")
        seed_system_foods()
        self.coffee = NutritionFoodItem.objects.get(name="Coffee")
        self.date = "2026-06-09"

    def create_meal_record(self, meal_type="breakfast", serving_ratio="1"):
        payload = {
            "member_id": self.member.id,
            "meal_type": meal_type,
            "consumed_at": f"{self.date}T08:10:00+08:00",
            "source": "manual",
            "meal_foods": [
                {
                    "food_item_id": self.coffee.id,
                    "serving_ratio": serving_ratio,
                    "serving_description": "1杯（237毫升）",
                }
            ],
        }
        response = self.client.post("/api/v1/nutrition/meal-records/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response.json()["data"]


class NutritionDashboardAPITests(NutritionAPITestBase):
    def test_dashboard_empty_day(self):
        response = self.client.get(f"/api/v1/nutrition/dashboard/?member_id={self.member.id}&date={self.date}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["goal"]["energy_kcal"], 1995)
        self.assertEqual(len(data["meals"]), 4)
        self.assertEqual(data["server_intake"]["energy_kcal"], 0)

    def test_dashboard_reflects_meal_record(self):
        self.create_meal_record()
        response = self.client.get(f"/api/v1/nutrition/dashboard/?member_id={self.member.id}&date={self.date}")
        data = response.json()["data"]
        self.assertEqual(data["server_intake"]["energy_kcal"], 2)
        breakfast = next(item for item in data["meals"] if item["meal_type"] == "breakfast")
        self.assertEqual(breakfast["record_count"], 1)
        self.assertIn("咖啡", breakfast["food_summary"])


class NutritionMealRecordAPITests(NutritionAPITestBase):
    def test_list_meal_records_empty(self):
        response = self.client.get(f"/api/v1/nutrition/meal-records/?member_id={self.member.id}&date={self.date}&meal_type=breakfast")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["records"], [])
        self.assertEqual(data["overview"]["energy_kcal"], 0)

    def test_create_update_delete_meal_record(self):
        created = self.create_meal_record()
        record_id = created["id"]
        self.assertTrue(any(item["nutrient_type"] == "energy_kcal" for item in created["intakes"]))

        patch_response = self.client.patch(
            f"/api/v1/nutrition/meal-records/{record_id}/",
            {"title": "Updated breakfast"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.json()["data"]["title"], "Updated breakfast")

        delete_response = self.client.delete(f"/api/v1/nutrition/meal-records/{record_id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertTrue(delete_response.json()["data"]["deleted"])

        dashboard = self.client.get(f"/api/v1/nutrition/dashboard/?member_id={self.member.id}&date={self.date}").json()["data"]
        self.assertEqual(dashboard["server_intake"]["energy_kcal"], 0)


class NutritionSearchAPITests(NutritionAPITestBase):
    def test_text_search_finds_system_food(self):
        response = self.client.get(f"/api/v1/nutrition/search/?member_id={self.member.id}&mode=text&q=Coffee&type=food")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.json()["data"]["items"]
        self.assertTrue(any(item["food_item"]["name"] == "Coffee" for item in items))

    def test_empty_search_returns_preset_foods(self):
        response = self.client.get(f"/api/v1/nutrition/search/?member_id={self.member.id}&mode=text&q=&type=food")
        self.assertGreaterEqual(len(response.json()["data"]["items"]), 5)

    def test_barcode_search(self):
        apple = NutritionFoodItem.objects.get(name="Apple")
        response = self.client.get(
            f"/api/v1/nutrition/search/?member_id={self.member.id}&mode=barcode&q={apple.barcode}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.json()["data"]["items"]
        self.assertEqual(items[0]["food_item"]["id"], apple.id)

    def test_favorite_flow(self):
        add_response = self.client.post(
            "/api/v1/nutrition/favorites/",
            {"target_type": "nutrition_food_item", "target_id": self.coffee.id},
            format="json",
        )
        self.assertEqual(add_response.status_code, status.HTTP_201_CREATED)
        search_response = self.client.get(
            f"/api/v1/nutrition/search/?member_id={self.member.id}&mode=text&q=Coffee&favorite=true&type=food"
        )
        self.assertEqual(len(search_response.json()["data"]["items"]), 1)
        delete_response = self.client.delete(
            f"/api/v1/nutrition/favorites/?target_type=nutrition_food_item&target_id={self.coffee.id}"
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)


class NutritionCustomItemAPITests(NutritionAPITestBase):
    def test_create_custom_food_and_search(self):
        payload = {
            "name": "Homemade Rice",
            "localized_name": "自制饭",
            "serving_description": "1份",
            "intakes": [
                {"nutrient_type": "energy_kcal", "value": 520, "unit": "kcal"},
                {"nutrient_type": "protein_g", "value": 20, "unit": "g"},
                {"nutrient_type": "carbohydrate_g", "value": 70, "unit": "g"},
                {"nutrient_type": "fat_g", "value": 10, "unit": "g"},
            ],
        }
        response = self.client.post("/api/v1/nutrition/food-items/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        food_id = response.json()["data"]["food_item"]["id"]
        search = self.client.get(
            f"/api/v1/nutrition/search/?member_id={self.member.id}&mode=text&q=Homemade&type=food&created_by_me=true"
        )
        self.assertTrue(any(item["food_item"]["id"] == food_id for item in search.json()["data"]["items"]))


class NutritionEnergyBurnAPITests(NutritionAPITestBase):
    def test_energy_burn_crud_and_apple_health_id(self):
        create_payload = {
            "member_id": self.member.id,
            "burned_at": f"{self.date}T18:30:00+08:00",
            "energy_kcal": 230,
            "activity_type": "walking",
            "duration_seconds": 1800,
            "source": "manual",
            "note": "walk",
        }
        create_response = self.client.post("/api/v1/nutrition/energy-burn-records/", create_payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        record_id = create_response.json()["data"]["id"]

        list_response = self.client.get(f"/api/v1/nutrition/energy-burn-records/?member_id={self.member.id}&date={self.date}")
        self.assertEqual(len(list_response.json()["data"]["records"]), 1)

        patch_response = self.client.patch(
            f"/api/v1/nutrition/energy-burn-records/{record_id}/",
            {"energy_kcal": 250},
            format="json",
        )
        self.assertEqual(patch_response.json()["data"]["energy_kcal"], 250.0)

        writeback = self.client.post(
            f"/api/v1/nutrition/energy-burn-records/{record_id}/apple-health-id/",
            {"apple_health_id": "HK-burn-001"},
            format="json",
        )
        self.assertEqual(writeback.status_code, status.HTTP_200_OK)
        self.assertEqual(writeback.json()["data"]["apple_health_id"], "HK-burn-001")

        delete_response = self.client.delete(f"/api/v1/nutrition/energy-burn-records/{record_id}/")
        self.assertTrue(delete_response.json()["data"]["deleted"])


class NutritionAppleHealthImportAPITests(NutritionAPITestBase):
    def test_import_intake_and_energy_burn_idempotent(self):
        intake_payload = {
            "member_id": self.member.id,
            "samples": [
                {
                    "apple_health_id": "HK-uuid-001",
                    "occurred_at": f"{self.date}T08:00:00+08:00",
                    "source_bundle_id": "com.example.food",
                    "source_name": "Other Food App",
                    "intakes": [{"nutrient_type": "energy_kcal", "value": 120, "unit": "kcal"}],
                }
            ],
        }
        first = self.client.post("/api/v1/nutrition/apple-health/intake-imports/", intake_payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post("/api/v1/nutrition/apple-health/intake-imports/", intake_payload, format="json")
        self.assertEqual(second.json()["code"], 40901)

        dashboard = self.client.get(f"/api/v1/nutrition/dashboard/?member_id={self.member.id}&date={self.date}").json()["data"]
        self.assertEqual(dashboard["apple_health_external_intake"]["energy_kcal"], 120)

        burn_payload = {
            "member_id": self.member.id,
            "samples": [
                {
                    "apple_health_id": "HK-burn-001",
                    "burned_at": f"{self.date}T18:00:00+08:00",
                    "energy_kcal": 411,
                    "activity_type": "active_energy",
                    "source": "apple_health_import",
                }
            ],
        }
        burn_first = self.client.post("/api/v1/nutrition/apple-health/energy-burn-imports/", burn_payload, format="json")
        self.assertEqual(burn_first.status_code, status.HTTP_201_CREATED)
        burn_second = self.client.post("/api/v1/nutrition/apple-health/energy-burn-imports/", burn_payload, format="json")
        self.assertEqual(burn_second.json()["code"], 40901)

    def test_intake_apple_health_id_writeback(self):
        created = self.create_meal_record()
        intake_id = created["intakes"][0]["id"]
        response = self.client.post(
            f"/api/v1/nutrition/intakes/{intake_id}/apple-health-id/",
            {"apple_health_id": "HK-nutrition-sample-001"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["apple_health_id"], "HK-nutrition-sample-001")


class NutritionMealHistoryAPITests(NutritionAPITestBase):
    def test_list_meal_records_history_by_date_range(self):
        self.create_meal_record(meal_type="breakfast")
        response = self.client.get(
            f"/api/v1/nutrition/meal-records/?member_id={self.member.id}&date_from=2026-06-01&date_to={self.date}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["member_id"], self.member.id)
        self.assertEqual(data["date_from"], "2026-06-01")
        self.assertEqual(data["date_to"], self.date)
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["meal_type"], "breakfast")


class NutritionETagAPITests(NutritionAPITestBase):
    def _assert_etag_roundtrip(self, url: str):
        first = self.client.get(url)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        etag = first.headers.get("ETag")
        self.assertTrue(etag)
        self.assertIn("private", first.headers.get("Cache-Control", ""))

        second = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(second.status_code, status.HTTP_304_NOT_MODIFIED)
        self.assertEqual(second.headers.get("ETag"), etag)
        self.assertEqual(second.content, b"")

    def test_defaults_etag_and_304(self):
        url = f"/api/v1/nutrition/defaults/?member_id={self.member.id}"
        self._assert_etag_roundtrip(url)

    def test_dashboard_etag_and_304(self):
        url = f"/api/v1/nutrition/dashboard/?member_id={self.member.id}&date={self.date}"
        self._assert_etag_roundtrip(url)

    def test_meal_records_etag_and_304(self):
        self.create_meal_record(meal_type="breakfast")
        url = f"/api/v1/nutrition/meal-records/?member_id={self.member.id}&date={self.date}"
        self._assert_etag_roundtrip(url)

    def test_meal_records_history_etag_and_304(self):
        self.create_meal_record(meal_type="breakfast")
        url = f"/api/v1/nutrition/meal-records/?member_id={self.member.id}&date_from=2026-06-01&date_to={self.date}"
        self._assert_etag_roundtrip(url)

    def test_energy_burn_etag_and_304(self):
        payload = {
            "member_id": self.member.id,
            "burned_at": f"{self.date}T09:00:00+08:00",
            "energy_kcal": 120,
            "activity_type": "manual",
            "note": "",
        }
        create_response = self.client.post("/api/v1/nutrition/energy-burn-records/", payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        url = f"/api/v1/nutrition/energy-burn-records/?member_id={self.member.id}&date={self.date}"
        first = self.client.get(url)
        etag = first.headers["ETag"]

        second = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(second.status_code, status.HTTP_304_NOT_MODIFIED)

        record_id = create_response.json()["data"]["id"]
        patch_response = self.client.patch(
            f"/api/v1/nutrition/energy-burn-records/{record_id}/",
            {"energy_kcal": 150},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)

        third = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(third.status_code, status.HTTP_200_OK)
        self.assertNotEqual(third.headers.get("ETag"), etag)
