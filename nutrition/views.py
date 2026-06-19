import logging
from datetime import datetime

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import error_response, success_response
from medical.services.member_permission_service import MemberPermissionDenied
from nutrition.constants import (
    NUTRITION_ERROR_DUPLICATE_APPLE_HEALTH_SAMPLE,
    NUTRITION_ERROR_INVALID_BARCODE,
    NUTRITION_ERROR_MEMBER_PERMISSION_DENIED,
    NUTRITION_ERROR_RECORD_NOT_FOUND,
)
from nutrition.permissions import NutritionPermissionGate
from nutrition.serializers import (
    AppleHealthEnergyBurnImportSerializer,
    AppleHealthIdSerializer,
    AppleHealthIntakeImportSerializer,
    EnergyBurnCreateSerializer,
    EnergyBurnUpdateSerializer,
    FavoriteSerializer,
    FoodItemCreateSerializer,
    MealRecordCreateSerializer,
    MealRecordUpdateSerializer,
    NutritionGoalSerializer,
    NutritionGoalCalculationSerializer,
    NutritionGoalUpsertSerializer,
    RecipeCreateSerializer,
)
from nutrition.services.dashboard_service import build_dashboard
from nutrition.services.energy_burn_service import (
    create_energy_burn_record,
    delete_energy_burn_record,
    import_apple_health_energy_burns,
    import_apple_health_intakes,
    list_energy_burn_records,
    update_energy_burn_record,
    write_energy_burn_apple_health_id,
    write_intake_apple_health_id,
)
from nutrition.services.food_recipe_service import create_custom_food, create_custom_recipe
from nutrition.services.goal_calculation_service import GoalCalculationInput, calculate_body_metrics, calculate_energy
from nutrition.services.goal_service import (
    GOAL_TARGET_SAFETY_VERSION,
    get_active_goal,
    resolve_goal_payload,
    resolve_meal_macro_targets,
    upsert_goal,
)
from nutrition.services.meal_record_service import create_meal_record, delete_meal_record, list_meal_records, list_meal_records_history, update_meal_record
from nutrition.services.search_service import add_favorite, remove_favorite, search_items
from nutrition.services.seed_data import SYSTEM_FOODS
from nutrition.http_cache import (
    build_dashboard_etag_payload,
    build_defaults_etag_payload,
    build_energy_burn_etag_payload,
    build_meal_records_etag_payload,
)

logger = logging.getLogger("nutrition.api")


class NutritionAPIView(APIView):
    permission_classes = [IsAuthenticated]
    etag_max_age = 86400

    def parse_member_id(self, request, *, required=True):
        raw = request.query_params.get("member_id") if request.method == "GET" else (request.data.get("member_id") if hasattr(request, "data") else None)
        if raw is None and request.method in {"POST", "PATCH", "DELETE"}:
            raw = request.data.get("member_id")
        if raw is None and not required:
            return None
        if raw is None:
            return None, error_response(msg="member_id_required", code=-1, status_code=400)
        try:
            return int(raw), None
        except (TypeError, ValueError):
            return None, error_response(msg="invalid_member_id", code=-1, status_code=400)

    def parse_date(self, request, *, required=True):
        raw = request.query_params.get("date")
        if raw is None and required:
            return None, error_response(msg="date_required", code=-1, status_code=400)
        if raw is None:
            return None, None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date(), None
        except ValueError:
            return None, error_response(msg="invalid_date", code=-1, status_code=400)

    def parse_date_range(self, request):
        raw_from = request.query_params.get("date_from")
        raw_to = request.query_params.get("date_to")
        if raw_from is None or raw_to is None:
            return None, None, None
        try:
            date_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
            date_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
        except ValueError:
            return None, None, error_response(msg="invalid_date", code=-1, status_code=400)
        if date_from > date_to:
            return None, None, error_response(msg="invalid_date_range", code=-1, status_code=400)
        return date_from, date_to, None

    def require_view(self, request, member_id):
        try:
            NutritionPermissionGate.require_view(request.user, member_id)
            return None
        except (MemberPermissionDenied, PermissionError):
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)

    def require_write(self, request, member_id):
        try:
            NutritionPermissionGate.require_write(request.user, member_id)
            return None
        except (MemberPermissionDenied, PermissionError):
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)

    def require_edit(self, request, member_id):
        try:
            NutritionPermissionGate.require_edit(request.user, member_id)
            return None
        except (MemberPermissionDenied, PermissionError):
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)

    def require_delete(self, request, member_id):
        try:
            NutritionPermissionGate.require_delete(request.user, member_id)
            return None
        except (MemberPermissionDenied, PermissionError):
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)

    def log(self, request, event: str, **kwargs):
        logger.info(
            "nutrition.%s request_id=%s user_id=%s %s",
            event,
            getattr(request, "request_id", ""),
            request.user.id,
            " ".join(f"{key}={value}" for key, value in kwargs.items()),
        )

    def _build_etag(self, request, payload: dict) -> str:
        return build_etag(
            {
                "path": request.path,
                "query": request.query_params.dict(),
                "user_id": request.user.id,
                **payload,
            }
        )

    def _is_not_modified(self, request, etag: str) -> bool:
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming == "":
            return False
        return incoming == normalize_etag(etag)

    def _set_cache_headers(self, response, etag: str):
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={self.etag_max_age}"

    def _not_modified_response(self, etag: str):
        response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
        response.content = b""
        self._set_cache_headers(response, etag)
        return response

    def _cached_success_response(self, request, payload: dict, data):
        etag = self._build_etag(request, payload)
        if self._is_not_modified(request, etag):
            return self._not_modified_response(etag)
        response = success_response(data)
        self._set_cache_headers(response, etag)
        return response


class NutritionHealthAPIView(NutritionAPIView):
    def get(self, request):
        self.log(request, "health")
        return success_response({"module": "nutrition", "status": "ok", "request_id": getattr(request, "request_id", ""), "preset_food_count": len(SYSTEM_FOODS)})


class NutritionDefaultsPreviewAPIView(NutritionAPIView):
    def get(self, request):
        member_id, err = self.parse_member_id(request)
        if err:
            return err
        if perm := self.require_view(request, member_id):
            return perm
        data = {
            "member_id": member_id,
            "goal": resolve_goal_payload(request.user, member_id),
            "meal_targets": resolve_meal_macro_targets(request.user, member_id),
        }
        self.log(request, "defaults_preview", member_id=member_id)
        return self._cached_success_response(
            request,
            build_defaults_etag_payload(request.user, member_id),
            data,
        )


class NutritionGoalAPIView(NutritionAPIView):
    def get(self, request):
        member_id, err = self.parse_member_id(request)
        if err:
            return err
        if perm := self.require_view(request, member_id):
            return perm
        goal = get_active_goal(request.user, member_id)
        data = {
            "member_id": member_id,
            "goal": NutritionGoalSerializer(goal).data if goal else None,
            "defaults": resolve_goal_payload(request.user, member_id),
        }
        self.log(request, "goal_get", member_id=member_id, goal_id=goal.id if goal else 0)
        return self._cached_success_response(
            request,
            {"goal": [goal.id, goal.updated_at.isoformat()] if goal else None, "version": GOAL_TARGET_SAFETY_VERSION},
            data,
        )

    def post(self, request):
        serializer = NutritionGoalUpsertSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        payload = serializer.validated_data
        if perm := self.require_write(request, payload["member_id"]):
            return perm
        goal = upsert_goal(
            request.user,
            payload["member_id"],
            goal_type=payload["goal_type"],
            height_cm=payload.get("height_cm"),
            current_weight_kg=payload.get("current_weight_kg"),
            target_weight_kg=payload.get("target_weight_kg"),
            biological_sex=payload.get("biological_sex", ""),
            age_years=payload.get("age_years"),
            activity_level=payload.get("activity_level", ""),
            weekly_weight_delta_kg=payload.get("weekly_weight_delta_kg"),
            bmr_kcal=payload.get("bmr_kcal"),
            tdee_kcal=payload.get("tdee_kcal"),
            energy_delta_kcal=payload.get("energy_delta_kcal"),
            calculation_formula=payload.get("calculation_formula", ""),
            calculation_version=payload.get("calculation_version", ""),
            calculation_inputs=payload.get("calculation_inputs"),
            is_energy_target_custom=payload.get("is_energy_target_custom", False),
            weekend_energy_target_kcal=payload.get("weekend_energy_target_kcal"),
            is_weekend_energy_enabled=payload.get("is_weekend_energy_enabled", False),
            step_target=payload.get("step_target"),
            daily_energy_target_kcal=payload.get("daily_energy_target_kcal"),
            carbohydrate_target_g=payload.get("carbohydrate_target_g"),
            protein_target_g=payload.get("protein_target_g"),
            fat_target_g=payload.get("fat_target_g"),
            meal_distribution=payload.get("meal_distribution"),
            effective_from=payload.get("effective_from"),
            is_active=payload.get("is_active", True),
        )
        self.log(request, "goal_upsert", member_id=payload["member_id"], goal_id=goal.id, goal_type=goal.goal_type)
        return success_response(NutritionGoalSerializer(goal).data, status_code=status.HTTP_201_CREATED)


class NutritionGoalCalculateEnergyAPIView(NutritionAPIView):
    def post(self, request):
        serializer = NutritionGoalCalculationSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        payload = serializer.validated_data
        if perm := self.require_view(request, payload["member_id"]):
            return perm
        result = calculate_energy(_goal_calculation_input(request.user, payload))
        missing_fields = result.get("calculation_inputs", {}).get("missing_fields", [])
        self.log(
            request,
            "goal_calculate_energy",
            member_id=payload["member_id"],
            goal_type=payload.get("goal_type"),
            missing_fields=",".join(missing_fields),
        )
        return success_response(result)


class NutritionGoalCalculateBodyMetricsAPIView(NutritionAPIView):
    def post(self, request):
        serializer = NutritionGoalCalculationSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        payload = serializer.validated_data
        if perm := self.require_view(request, payload["member_id"]):
            return perm
        result = calculate_body_metrics(_goal_calculation_input(request.user, payload))
        self.log(
            request,
            "goal_calculate_body_metrics",
            member_id=payload["member_id"],
            goal_type=payload.get("goal_type"),
            missing_fields=",".join(result["missing_fields"]),
        )
        return success_response(result)


def _goal_calculation_input(user, payload):
    return GoalCalculationInput(
        user=user,
        member_id=payload["member_id"],
        goal_type=payload.get("goal_type") or "maintain",
        activity_level=payload.get("activity_level") or "low",
        current_weight_kg=payload.get("current_weight_kg"),
        height_cm=payload.get("height_cm"),
        biological_sex=payload.get("biological_sex"),
        age_years=payload.get("age_years"),
        weekly_weight_delta_kg=payload.get("weekly_weight_delta_kg"),
        target_weight_kg=payload.get("target_weight_kg"),
    )


class NutritionDashboardAPIView(NutritionAPIView):
    def get(self, request):
        member_id, err = self.parse_member_id(request)
        if err:
            return err
        local_day, err = self.parse_date(request)
        if err:
            return err
        if perm := self.require_view(request, member_id):
            return perm
        data = build_dashboard(request.user, member_id, local_day)
        self.log(request, "dashboard", member_id=member_id, date=local_day.isoformat())
        return self._cached_success_response(
            request,
            build_dashboard_etag_payload(request.user, member_id, local_day),
            data,
        )


class NutritionMealRecordListCreateAPIView(NutritionAPIView):
    def get(self, request):
        member_id, err = self.parse_member_id(request)
        if err:
            return err
        if perm := self.require_view(request, member_id):
            return perm

        date_from, date_to, range_err = self.parse_date_range(request)
        if range_err:
            return range_err
        if date_from and date_to:
            data = list_meal_records_history(request.user, member_id, date_from, date_to)
            self.log(
                request,
                "meal_records_history",
                member_id=member_id,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
            )
            return self._cached_success_response(
                request,
                build_meal_records_etag_payload(
                    request.user,
                    member_id,
                    date_from=date_from,
                    date_to=date_to,
                ),
                data,
            )

        local_day, err = self.parse_date(request)
        if err:
            return err
        meal_type = request.query_params.get("meal_type") or None
        data = list_meal_records(request.user, member_id, local_day, meal_type)
        self.log(request, "meal_records_list", member_id=member_id, date=local_day.isoformat(), meal_type=meal_type or "")
        return self._cached_success_response(
            request,
            build_meal_records_etag_payload(
                request.user,
                member_id,
                local_day=local_day,
                meal_type=meal_type,
            ),
            data,
        )

    def post(self, request):
        serializer = MealRecordCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        payload = serializer.validated_data
        if perm := self.require_write(request, payload["member_id"]):
            return perm
        data = create_meal_record(request.user, payload)
        self.log(request, "meal_record_create", member_id=payload["member_id"], record_id=data["id"])
        return success_response(data, status_code=status.HTTP_201_CREATED)


class NutritionMealRecordDetailAPIView(NutritionAPIView):
    def patch(self, request, record_id: int):
        serializer = MealRecordUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        from nutrition.models import NutritionMealRecord

        record = NutritionMealRecord.objects.filter(id=record_id, user=request.user, is_deleted=False).first()
        if record is None:
            return error_response(msg="nutrition_record_not_found", code=NUTRITION_ERROR_RECORD_NOT_FOUND, status_code=404)
        if perm := self.require_edit(request, record.member_id):
            return perm
        data = update_meal_record(request.user, record_id, serializer.validated_data)
        self.log(request, "meal_record_update", record_id=record_id)
        return success_response(data)

    def delete(self, request, record_id: int):
        from nutrition.models import NutritionMealRecord

        record = NutritionMealRecord.objects.filter(id=record_id, user=request.user, is_deleted=False).first()
        if record is None:
            return error_response(msg="nutrition_record_not_found", code=NUTRITION_ERROR_RECORD_NOT_FOUND, status_code=404)
        if perm := self.require_delete(request, record.member_id):
            return perm
        data = delete_meal_record(request.user, record_id)
        self.log(request, "meal_record_delete", record_id=record_id)
        return success_response(data)


class NutritionSearchAPIView(NutritionAPIView):
    def get(self, request):
        member_id, err = self.parse_member_id(request)
        if err:
            return err
        if perm := self.require_view(request, member_id):
            return perm
        mode = request.query_params.get("mode") or "text"
        query = request.query_params.get("q", "")
        result = search_items(
            request.user,
            member_id=member_id,
            mode=mode,
            query=query,
            result_type=request.query_params.get("type") or "all",
            favorite_only=request.query_params.get("favorite", "false").lower() in {"1", "true", "yes"},
            created_by_me=request.query_params.get("created_by_me", "false").lower() in {"1", "true", "yes"},
        )
        if result.get("error_code") == NUTRITION_ERROR_INVALID_BARCODE:
            return error_response(msg="invalid_barcode", code=NUTRITION_ERROR_INVALID_BARCODE, status_code=400)
        self.log(request, "search", member_id=member_id, mode=mode, query=query, count=len(result.get("items", [])))
        return success_response(result)


class NutritionFavoriteAPIView(NutritionAPIView):
    def post(self, request):
        serializer = FavoriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        data = add_favorite(request.user, serializer.validated_data["target_type"], serializer.validated_data["target_id"])
        self.log(request, "favorite_add", target_type=data["target_type"], target_id=data["target_id"])
        return success_response(data, status_code=status.HTTP_201_CREATED)

    def delete(self, request):
        target_type = request.query_params.get("target_type")
        target_id = request.query_params.get("target_id")
        if not target_type or not target_id:
            return error_response(msg="target_required", code=-1, status_code=400)
        try:
            target_id_int = int(target_id)
        except ValueError:
            return error_response(msg="invalid_target_id", code=-1, status_code=400)
        data = remove_favorite(request.user, target_type, target_id_int)
        self.log(request, "favorite_remove", target_type=target_type, target_id=target_id_int)
        return success_response(data)


class NutritionFoodItemCreateAPIView(NutritionAPIView):
    def post(self, request):
        serializer = FoodItemCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        data = create_custom_food(request.user, serializer.validated_data)
        self.log(request, "food_item_create", food_item_id=data["food_item"]["id"])
        return success_response(data, status_code=status.HTTP_201_CREATED)


class NutritionRecipeCreateAPIView(NutritionAPIView):
    def post(self, request):
        serializer = RecipeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        data = create_custom_recipe(request.user, serializer.validated_data)
        self.log(request, "recipe_create", recipe_id=data["recipe"]["id"])
        return success_response(data, status_code=status.HTTP_201_CREATED)


class NutritionEnergyBurnListCreateAPIView(NutritionAPIView):
    def get(self, request):
        member_id, err = self.parse_member_id(request)
        if err:
            return err
        local_day, err = self.parse_date(request)
        if err:
            return err
        if perm := self.require_view(request, member_id):
            return perm
        data = list_energy_burn_records(request.user, member_id, local_day)
        self.log(request, "energy_burn_list", member_id=member_id, date=local_day.isoformat())
        return self._cached_success_response(
            request,
            build_energy_burn_etag_payload(request.user, member_id, local_day),
            data,
        )

    def post(self, request):
        serializer = EnergyBurnCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        payload = serializer.validated_data
        if perm := self.require_write(request, payload["member_id"]):
            return perm
        data = create_energy_burn_record(request.user, payload)
        self.log(request, "energy_burn_create", member_id=payload["member_id"], record_id=data["id"])
        return success_response(data, status_code=status.HTTP_201_CREATED)


class NutritionEnergyBurnDetailAPIView(NutritionAPIView):
    def patch(self, request, record_id: int):
        from nutrition.models import NutritionEnergyBurnRecord

        record = NutritionEnergyBurnRecord.objects.filter(id=record_id, user=request.user, is_deleted=False).first()
        if record is None:
            return error_response(msg="nutrition_record_not_found", code=NUTRITION_ERROR_RECORD_NOT_FOUND, status_code=404)
        serializer = EnergyBurnUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        if perm := self.require_edit(request, record.member_id):
            return perm
        data = update_energy_burn_record(request.user, record_id, serializer.validated_data)
        self.log(request, "energy_burn_update", record_id=record_id)
        return success_response(data)

    def delete(self, request, record_id: int):
        from nutrition.models import NutritionEnergyBurnRecord

        record = NutritionEnergyBurnRecord.objects.filter(id=record_id, user=request.user, is_deleted=False).first()
        if record is None:
            return error_response(msg="nutrition_record_not_found", code=NUTRITION_ERROR_RECORD_NOT_FOUND, status_code=404)
        if perm := self.require_delete(request, record.member_id):
            return perm
        data = delete_energy_burn_record(request.user, record_id)
        self.log(request, "energy_burn_delete", record_id=record_id)
        return success_response(data)


class NutritionAppleHealthIntakeImportAPIView(NutritionAPIView):
    def post(self, request):
        serializer = AppleHealthIntakeImportSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        payload = serializer.validated_data
        if perm := self.require_write(request, payload["member_id"]):
            return perm
        result = import_apple_health_intakes(request.user, payload["member_id"], payload["samples"])
        if result.get("error") == "not_self_member":
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)
        if result.get("duplicates"):
            self.log(request, "apple_health_intake_import_duplicate", member_id=payload["member_id"], duplicate_count=len(result["duplicates"]))
            return success_response(result, msg="duplicate_apple_health_sample", code=NUTRITION_ERROR_DUPLICATE_APPLE_HEALTH_SAMPLE)
        self.log(request, "apple_health_intake_import", member_id=payload["member_id"], imported_count=len(result.get("imported", [])))
        return success_response(result, status_code=status.HTTP_201_CREATED)


class NutritionAppleHealthEnergyBurnImportAPIView(NutritionAPIView):
    def post(self, request):
        serializer = AppleHealthEnergyBurnImportSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        payload = serializer.validated_data
        if perm := self.require_write(request, payload["member_id"]):
            return perm
        result = import_apple_health_energy_burns(request.user, payload["member_id"], payload["samples"])
        if result.get("error") == "not_self_member":
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)
        if result.get("duplicates"):
            self.log(request, "apple_health_burn_import_duplicate", member_id=payload["member_id"], duplicate_count=len(result["duplicates"]))
            return success_response(result, msg="duplicate_apple_health_sample", code=NUTRITION_ERROR_DUPLICATE_APPLE_HEALTH_SAMPLE)
        self.log(request, "apple_health_burn_import", member_id=payload["member_id"], imported_count=len(result.get("imported", [])))
        return success_response(result, status_code=status.HTTP_201_CREATED)


class NutritionIntakeAppleHealthIdAPIView(NutritionAPIView):
    def post(self, request, intake_id: int):
        serializer = AppleHealthIdSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        result = write_intake_apple_health_id(request.user, intake_id, serializer.validated_data["apple_health_id"])
        if result is None:
            return error_response(msg="nutrition_record_not_found", code=NUTRITION_ERROR_RECORD_NOT_FOUND, status_code=404)
        if result.get("error") == "not_self_member":
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)
        self.log(request, "intake_apple_health_id", intake_id=intake_id)
        return success_response(result)


class NutritionEnergyBurnAppleHealthIdAPIView(NutritionAPIView):
    def post(self, request, record_id: int):
        serializer = AppleHealthIdSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(msg="validation_error", code=-1, status_code=400, data=serializer.errors)
        result = write_energy_burn_apple_health_id(request.user, record_id, serializer.validated_data["apple_health_id"])
        if result is None:
            return error_response(msg="nutrition_record_not_found", code=NUTRITION_ERROR_RECORD_NOT_FOUND, status_code=404)
        if result.get("error") == "not_self_member":
            return error_response(msg="member_permission_denied", code=NUTRITION_ERROR_MEMBER_PERMISSION_DENIED, status_code=403)
        self.log(request, "energy_burn_apple_health_id", record_id=record_id)
        return success_response(result)
