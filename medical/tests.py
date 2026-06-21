from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from medical.models import (
    MedicalCase,
    MedicationPlan,
    MedicineBox,
    Member,
    MemberMedicalProfile,
    MemberModuleSetting,
    Prescription,
    UserMemberBinding,
)

User = get_user_model()


class CombinedMedicalCreateAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="medical_tester",
            email="medical@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)

    def test_combined_create_saves_prescription_box_and_plan_from_current_contract(self):
        payload = {
            "member": {
                "name": "赵道凯",
                "gender": "male",
                "relationship": "self",
            },
            "medical_case": {
                "title": "就诊病例",
                "hospital_name": "苏州大学附属第四医院",
                "diagnosis_summary": "前庭性眩晕，予甲磺酸倍他司汀片治疗。",
            },
            "prescriptions": [
                {
                "institution_name": "苏州大学附属第四医院",
                "prescribed_at": "2025-08-02",
                "diagnosis": "前庭性眩晕",
                "medication_plans": [
                    {
                        "drug_name": "甲磺酸倍他司汀片",
                        "dose_per_time": "1 片",
                        "dose_value": "1",
                        "dose_unit": "片",
                        "frequency_type": "daily",
                        "frequency_text": "每日三次",
                        "reminder_times": [{"time": "08:00", "dose": 1}],
                        "start_date": "2025-08-02",
                        "instructions": "餐后口服",
                        "medicine_box": {
                            "medicine_name": "甲磺酸倍他司汀片",
                            "dosage_form": "片剂",
                            "dose_unit": "片",
                        },
                    }
                ],
                }
            ],
        }

        response = self.client.post("/api/v1/medical/combined-create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(len(body["prescription_ids"]), 1)
        self.assertEqual(len(body["medicine_box_ids"]), 1)
        self.assertEqual(len(body["medication_plan_ids"]), 1)
        prescription = Prescription.objects.get(id=body["prescription_ids"][0])
        medicine_box = MedicineBox.objects.get(id=body["medicine_box_ids"][0])
        plan = MedicationPlan.objects.get(id=body["medication_plan_ids"][0])

        self.assertEqual(prescription.institution_name, "苏州大学附属第四医院")
        self.assertEqual(medicine_box.medicine_name, "甲磺酸倍他司汀片")
        self.assertEqual(plan.prescription_id, prescription.id)
        self.assertEqual(plan.medicine_box_id, medicine_box.id)
        self.assertEqual(plan.drug_name, "甲磺酸倍他司汀片")

    def test_combined_create_medication_plan_without_medicine_box_when_explicitly_null(self):
        payload = {
            "member": {
                "name": "赵道凯",
                "gender": "male",
                "relationship": "self",
            },
            "medical_case": {
                "title": "就诊病例",
                "diagnosis_summary": "前庭性眩晕，予甲磺酸倍他司汀片治疗。",
            },
            "prescriptions": [
                {
                    "institution_name": "苏州大学附属第四医院",
                    "prescribed_at": "2025-08-02",
                    "diagnosis": "前庭性眩晕",
                    "medication_plans": [
                        {
                            "drug_name": "甲磺酸倍他司汀片",
                            "dose_per_time": "1 片",
                            "dose_value": "1",
                            "dose_unit": "片",
                            "frequency_type": "daily",
                            "frequency_text": "每日三次",
                            "reminder_times": [{"time": "08:00", "dose": 1}],
                            "start_date": "2025-08-02",
                            "instructions": "餐后口服",
                            "medicine_box": None,
                        }
                    ],
                }
            ],
        }

        response = self.client.post("/api/v1/medical/combined-create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(len(body["prescription_ids"]), 1)
        self.assertEqual(len(body["medicine_box_ids"]), 0)
        self.assertEqual(len(body["medication_plan_ids"]), 1)
        self.assertEqual(MedicineBox.objects.count(), 0)
        plan = MedicationPlan.objects.get(id=body["medication_plan_ids"][0])
        self.assertIsNone(plan.medicine_box_id)
        self.assertEqual(plan.drug_name, "甲磺酸倍他司汀片")


class MemberCompleteDataAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="complete_data_tester",
            email="complete_data@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)

    def test_complete_data_includes_medications_on_linked_medical_case(self):
        member = Member.objects.create(user=self.user, name="测试成员")
        UserMemberBinding.objects.create(user=self.user, member=member, relationship="self")
        medical_case = MedicalCase.objects.create(
            user=self.user,
            member=member,
            title="就诊病例",
            hospital_name="苏州大学附属第四医院",
            diagnosis_summary="结膜炎",
        )
        prescription = Prescription.objects.create(
            user=self.user,
            member=member,
            medical_case=medical_case,
            institution_name="苏州大学附属第四医院",
            diagnosis="结膜炎",
            prescriber_name="赵道凯",
        )
        medicine_box = MedicineBox.objects.create(
            user=self.user,
            member=member,
            medicine_name="普拉洛芬滴眼液",
            dose_unit="滴",
        )
        MedicationPlan.objects.create(
            user=self.user,
            member=member,
            medical_case=medical_case,
            medicine_box=medicine_box,
            prescription=prescription,
            drug_name="普拉洛芬滴眼液",
            dose_per_time="每次1滴",
            dose_unit="滴",
            frequency_type="daily",
            frequency_text="每日四次",
            start_date="2026-06-13",
        )

        response = self.client.get(f"/api/v1/medical/members/{member.id}/complete-data/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()["data"]
        case_payload = next(item for item in body["medical_cases"] if item["id"] == medical_case.id)
        self.assertEqual(case_payload["medications"], ["普拉洛芬滴眼液"])

    def test_complete_data_includes_member_medical_profile_and_module_settings(self):
        member = Member.objects.create(user=self.user, name="汇总成员", gender="female")
        UserMemberBinding.objects.create(user=self.user, member=member, relationship="self")
        profile = MemberMedicalProfile.objects.create(
            user=self.user,
            member=member,
            chronic_conditions=["高血压"],
            extra={"height_cm": "160", "weight_kg": "60", "sedentary_level": "medium"},
        )
        MemberModuleSetting.objects.create(
            user=self.user,
            member=member,
            module_code=MemberModuleSetting.ModuleCode.MEDICAL,
            is_enabled=True,
            is_completed=False,
            display_order=10,
        )

        response = self.client.get(f"/api/v1/medical/members/{member.id}/complete-data/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()["data"]
        self.assertIn("member_medical_profile", body)
        self.assertIn("member_module_settings", body)
        self.assertEqual(body["member_medical_profile"]["id"], profile.id)
        self.assertIn("guidance_sections", body["member_medical_profile"])
        self.assertEqual(len(body["member_medical_profile"]["guidance_sections"]), 5)
        self.assertEqual(body["member_module_settings"][0]["module_code"], "medical")
        self.assertNotIn("medical_guidance", body)
        self.assertIn("nutrition_goal_state", body)
        self.assertEqual(body["nutrition_goal_state"]["member_id"], member.id)
        self.assertIn("defaults", body["nutrition_goal_state"])

    def test_combined_create_does_not_accept_legacy_prescription_alias(self):
        payload = {
            "member": {
                "name": "赵道凯",
                "gender": "male",
                "relationship": "self",
            },
            "medical_case": {
                "title": "就诊病例",
                "diagnosis_summary": "结膜炎，予普拉洛芬滴眼液治疗。",
            },
            "prescription": {
                "institutionName": "苏州大学附属第四医院",
                "drugs": [{"medicineName": "普拉洛芬滴眼液"}],
            },
        }

        response = self.client.post("/api/v1/medical/combined-create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertNotIn("prescription_ids", body)
        self.assertEqual(Prescription.objects.count(), 0)
        self.assertEqual(MedicineBox.objects.count(), 0)
        self.assertEqual(MedicationPlan.objects.count(), 0)


class PrescriptionBatchWorkflowSaveAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="prescription_batch_tester",
            email="prescription_batch@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)

    def test_batch_save_prescriptions_without_medical_case(self):
        member = Member.objects.create(user=self.user, name="也很好")
        UserMemberBinding.objects.create(user=self.user, member=member, relationship="self")

        payload = {
            "member": member.id,
            "prescriptions": [
                {
                    "institution_name": "苏州大学附属第四医院",
                    "prescribed_at": "2026-04-20",
                    "diagnosis": "结膜炎",
                    "prescription_no": "0000349056",
                    "prescriber_name": "赵道凯",
                    "medication_plans": [
                        {
                            "drug_name": "普拉洛芬滴眼液（普南扑灵）",
                            "dose_per_time": "每次1滴",
                            "dose_value": "1",
                            "dose_unit": "滴",
                            "frequency_type": "daily",
                            "frequency_text": "每日四次",
                            "start_date": "2026-06-13",
                            "instructions": "滴眼",
                            "medicine_box": {
                                "medicine_name": "普拉洛芬滴眼液（普南扑灵）",
                                "dose_unit": "滴",
                            },
                        },
                        {
                            "drug_name": "盐酸氮卓斯汀滴眼液（爱赛平）",
                            "dose_per_time": "每次1滴",
                            "dose_value": "1",
                            "dose_unit": "滴",
                            "frequency_type": "daily",
                            "frequency_text": "每日两次",
                            "start_date": "2026-06-13",
                            "instructions": "滴眼",
                            "medicine_box": {
                                "medicine_name": "盐酸氮卓斯汀滴眼液（爱赛平）",
                                "dose_unit": "滴",
                            },
                        },
                    ],
                }
            ],
        }

        response = self.client.post(
            "/api/v1/medical/workflows/prescriptions/batch-save/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()["data"]
        self.assertEqual(body["member_id"], member.id)
        self.assertEqual(len(body["prescription_ids"]), 1)
        self.assertEqual(len(body["medicine_box_ids"]), 2)
        self.assertEqual(len(body["medication_plan_ids"]), 2)

        prescription = Prescription.objects.get(id=body["prescription_ids"][0])
        self.assertIsNone(prescription.medical_case_id)
        self.assertEqual(MedicationPlan.objects.filter(prescription_id=prescription.id).count(), 2)
        self.assertEqual(MedicalCase.objects.filter(member_id=member.id).count(), 0)

    def test_batch_save_skips_medicine_box_when_not_explicitly_provided(self):
        member = Member.objects.create(user=self.user, name="测试成员")
        UserMemberBinding.objects.create(user=self.user, member=member, relationship="self")

        payload = {
            "member": member.id,
            "prescriptions": [
                {
                    "institution_name": "苏州大学附属第四医院",
                    "diagnosis": "结膜炎",
                    "medication_plans": [
                        {
                            "drug_name": "普拉洛芬滴眼液（普南扑灵）",
                            "dose_per_time": "1滴",
                            "dose_unit": "滴",
                            "frequency_type": "daily",
                            "frequency_text": "每日四次",
                            "start_date": "2026-06-13",
                        },
                        {
                            "drug_name": "盐酸氮卓斯汀滴眼液（爱赛平）",
                            "dose_per_time": "1滴",
                            "dose_unit": "滴",
                            "frequency_type": "daily",
                            "frequency_text": "每日两次",
                            "start_date": "2026-06-13",
                            "medicine_box": {
                                "medicine_name": "盐酸氮卓斯汀滴眼液（爱赛平）",
                                "brand_name": "爱赛平",
                                "dosage_form": "滴眼液",
                                "dose_unit": "滴",
                            },
                        },
                    ],
                }
            ],
        }

        response = self.client.post(
            "/api/v1/medical/workflows/prescriptions/batch-save/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()["data"]
        self.assertEqual(len(body["medicine_box_ids"]), 1)
        self.assertEqual(len(body["medication_plan_ids"]), 2)

        plans = MedicationPlan.objects.filter(id__in=body["medication_plan_ids"]).order_by("id")
        self.assertIsNone(plans[0].medicine_box_id)
        self.assertEqual(plans[1].medicine_box_id, body["medicine_box_ids"][0])

    def test_batch_save_binds_medicine_box_file_ids(self):
        member = Member.objects.create(user=self.user, name="测试成员")
        UserMemberBinding.objects.create(user=self.user, member=member, relationship="self")
        box_file = ManagedFile.objects.create(user=self.user, original_name="medicine-box.jpg")
        plan_file = ManagedFile.objects.create(user=self.user, original_name="medication-plan.jpg")

        payload = {
            "member": member.id,
            "prescriptions": [
                {
                    "institution_name": "苏州大学附属第四医院",
                    "diagnosis": "结膜炎",
                    "medication_plans": [
                        {
                            "drug_name": "盐酸氮卓斯汀滴眼液（爱赛平）",
                            "dose_per_time": "1滴",
                            "dose_unit": "滴",
                            "frequency_type": "daily",
                            "frequency_text": "每日两次",
                            "start_date": "2026-06-13",
                            "file_ids": [plan_file.id],
                            "medicine_box": {
                                "medicine_name": "盐酸氮卓斯汀滴眼液（爱赛平）",
                                "brand_name": "爱赛平",
                                "dosage_form": "滴眼液",
                                "strength": "6ml:3mg (0.05%)",
                                "dose_unit": "滴",
                                "file_ids": [box_file.id],
                            },
                        }
                    ],
                }
            ],
        }

        response = self.client.post(
            "/api/v1/medical/workflows/prescriptions/batch-save/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()["data"]
        medicine_box = MedicineBox.objects.get(id=body["medicine_box_ids"][0])
        plan = MedicationPlan.objects.get(id=body["medication_plan_ids"][0])

        self.assertTrue(
            ManagedFileBusinessRelation.objects.filter(
                business_type="medicine_box",
                business_id=medicine_box.id,
                file_id=box_file.id,
            ).exists()
        )
        self.assertTrue(
            ManagedFileBusinessRelation.objects.filter(
                business_type="medication_plan",
                business_id=plan.id,
                file_id=plan_file.id,
            ).exists()
        )

    def test_batch_save_binds_existing_medicine_box_by_id(self):
        member = Member.objects.create(user=self.user, name="测试成员")
        UserMemberBinding.objects.create(user=self.user, member=member, relationship="self")
        existing_box = MedicineBox.objects.create(
            user=self.user,
            member=member,
            medicine_name="阿莫西林胶囊",
            brand_name="阿莫西林",
            dosage_form="胶囊",
            strength="0.25g x 24 粒",
            dose_unit="粒",
            total_quantity=12,
        )

        payload = {
            "member": member.id,
            "prescriptions": [
                {
                    "institution_name": "测试医院",
                    "diagnosis": "感染",
                    "medication_plans": [
                        {
                            "drug_name": "阿莫西林胶囊",
                            "dose_per_time": "2 粒",
                            "dose_unit": "粒",
                            "frequency_type": "daily",
                            "frequency_text": "每日三次",
                            "start_date": "2026-06-13",
                            "medicine_box_id": existing_box.id,
                        }
                    ],
                }
            ],
        }

        response = self.client.post(
            "/api/v1/medical/workflows/prescriptions/batch-save/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()["data"]
        self.assertEqual(body["medicine_box_ids"], [existing_box.id])
        self.assertEqual(MedicineBox.objects.filter(user=self.user).count(), 1)

        plan = MedicationPlan.objects.get(id=body["medication_plan_ids"][0])
        self.assertEqual(plan.medicine_box_id, existing_box.id)

    def test_batch_save_binds_family_cabinet_medicine_box_from_other_member(self):
        member_a = Member.objects.create(user=self.user, name="成员A")
        member_b = Member.objects.create(user=self.user, name="成员B")
        UserMemberBinding.objects.create(user=self.user, member=member_a, relationship="self")
        UserMemberBinding.objects.create(user=self.user, member=member_b, relationship="child")
        existing_box = MedicineBox.objects.create(
            user=self.user,
            member=member_a,
            medicine_name="普拉洛芬滴眼液（普南扑灵）",
            dosage_form="滴眼液",
            dose_unit="滴",
        )

        payload = {
            "member": member_b.id,
            "prescriptions": [
                {
                    "institution_name": "苏州大学附属第四医院",
                    "diagnosis": "结膜炎",
                    "medication_plans": [
                        {
                            "drug_name": "普拉洛芬滴眼液（普南扑灵）",
                            "dose_per_time": "1滴",
                            "dose_unit": "滴",
                            "frequency_type": "daily",
                            "frequency_text": "每日四次",
                            "start_date": "2026-06-13",
                            "medicine_box_id": existing_box.id,
                        }
                    ],
                }
            ],
        }

        response = self.client.post(
            "/api/v1/medical/workflows/prescriptions/batch-save/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()["data"]
        plan = MedicationPlan.objects.get(id=body["medication_plan_ids"][0])
        self.assertEqual(plan.member_id, member_b.id)
        self.assertEqual(plan.medicine_box_id, existing_box.id)

    def test_combined_create_binds_files_to_each_matched_business_type(self):
        files = {
            key: ManagedFile.objects.create(user=self.user, original_name=f"{key}.jpg")
            for key in ["case", "symptom", "visit", "surgery", "follow", "report", "prescription", "plan"]
        }
        payload = {
            "member": {"name": "赵道凯", "relationship": "self"},
            "medical_case": {
                "title": "就诊病例",
                "diagnosis_summary": "眩晕",
                "source_file_ids": [files["case"].id],
            },
            "symptom": {"name": "头晕", "source_file_ids": [files["symptom"].id]},
            "visit": {"visit_type": "outpatient", "source_file_ids": [files["visit"].id]},
            "surgery": {"procedure_name": "清创术", "source_file_ids": [files["surgery"].id]},
            "follow_up": {"status": "initial", "source_file_ids": [files["follow"].id]},
            "examination_reports": [
                {
                    "category": "exam",
                    "item_name": "CT",
                    "findings": "未见异常",
                    "source_file_ids": [files["report"].id],
                }
            ],
            "prescriptions": [
                {
                    "diagnosis": "眩晕",
                    "source_file_ids": [files["prescription"].id],
                    "medication_plans": [
                        {
                            "drug_name": "甲磺酸倍他司汀片",
                            "dose_per_time": "1 片",
                            "dose_unit": "片",
                            "frequency_type": "daily",
                            "frequency_text": "每日三次",
                            "start_date": "2025-08-02",
                            "medicine_box": {"medicine_name": "甲磺酸倍他司汀片", "dose_unit": "片"},
                            "file_ids": [files["plan"].id],
                        }
                    ],
                }
            ],
        }

        response = self.client.post("/api/v1/medical/combined-create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        expected = {
            "case": ("medical_case", body["medical_case_id"]),
            "symptom": ("symptom", body["symptom_id"]),
            "visit": ("visit", body["visit_id"]),
            "surgery": ("surgery", body["surgery_id"]),
            "follow": ("follow_up", body["follow_up_id"]),
            "report": ("examination_report", body["examination_report_ids"][0]),
            "prescription": ("prescription_batch", body["prescription_ids"][0]),
            "plan": ("medication_plan", body["medication_plan_ids"][0]),
        }
        for key, (business_type, business_id) in expected.items():
            self.assertTrue(
                ManagedFileBusinessRelation.objects.filter(
                    file=files[key],
                    user=self.user,
                    business_type=business_type,
                    business_id=str(business_id),
                ).exists()
            )


class MedicationPlanOptionalDoseFieldsAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="med_plan_optional_dose",
            email="optional-dose@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)
        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "测试成员", "gender": "male", "relationship": "self"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.member_id = create_resp.json()["data"]["id"]

    def test_create_medication_plan_allows_blank_dose_fields(self):
        payload = {
            "member": self.member_id,
            "drug_name": "v g哥哥",
            "dose_per_time": "",
            "dose_value": None,
            "dose_unit": "",
            "frequency_type": "daily",
            "frequency_text": "每天",
            "reminder_times": [{"time": "08:00"}],
            "start_date": "2026-06-17",
            "end_date": None,
            "instructions": "",
            "reminder_enabled": True,
            "status": "active",
            "extra": {},
            "weekly_weekdays": [],
            "every_n_days": None,
            "medicine_box": None,
            "prescription": None,
            "medical_case": None,
        }

        response = self.client.post(
            "/api/v1/medical/resources/?kind=medication-plans",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        plan = MedicationPlan.objects.get(id=response.json()["data"]["id"])
        self.assertEqual(plan.dose_per_time, "")
        self.assertEqual(plan.dose_unit, "")

    def test_patch_medication_plan_clears_deleted_medicine_box_reference(self):
        deleted_box = MedicineBox.objects.create(
            user=self.user,
            member_id=self.member_id,
            medicine_name="斯皮仁诺",
            dose_unit="",
        )
        deleted_box_id = deleted_box.id
        deleted_box.soft_delete()

        plan = MedicationPlan.objects.create(
            user=self.user,
            member_id=self.member_id,
            drug_name="斯皮仁诺",
            frequency_type="daily",
            frequency_text="每天2次",
            reminder_times=[{"time": "18:00"}, {"time": "18:40"}],
            start_date="2025-12-26",
            end_date="2025-12-28",
            instructions="口服",
            medicine_box_id=deleted_box_id,
        )

        payload = {
            "member": self.member_id,
            "drug_name": "斯皮仁诺",
            "dose_per_time": "",
            "dose_value": None,
            "dose_unit": "",
            "frequency_type": "daily",
            "frequency_text": "每天2次",
            "reminder_times": [{"time": "18:40"}, {"time": "18:00"}],
            "start_date": "2025-12-26",
            "end_date": "2025-12-28",
            "instructions": "口服",
            "reminder_enabled": True,
            "status": "active",
            "extra": {},
            "weekly_weekdays": [],
            "every_n_days": None,
            "medicine_box": deleted_box_id,
            "prescription": None,
            "medical_case": None,
        }

        response = self.client.patch(
            f"/api/v1/medical/resources/{plan.id}/?kind=medication-plans",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()["data"]
        self.assertIsNone(body["medicine_box"])
        plan.refresh_from_db()
        self.assertIsNone(plan.medicine_box_id)

    def test_get_medication_plan_with_deleted_medicine_box_returns_null(self):
        deleted_box = MedicineBox.objects.create(
            user=self.user,
            member_id=self.member_id,
            medicine_name="斯皮仁诺",
        )
        deleted_box_id = deleted_box.id
        deleted_box.soft_delete()

        plan = MedicationPlan.objects.create(
            user=self.user,
            member_id=self.member_id,
            drug_name="斯皮仁诺",
            frequency_type="daily",
            frequency_text="每天2次",
            reminder_times=[{"time": "18:00"}],
            start_date="2025-12-26",
            medicine_box_id=deleted_box_id,
        )

        response = self.client.get(
            f"/api/v1/medical/resources/{plan.id}/?kind=medication-plans",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertIsNone(response.json()["data"]["medicine_box"])

    def test_patch_medication_plan_clears_stale_medicine_box_without_payload_field(self):
        deleted_box = MedicineBox.objects.create(
            user=self.user,
            member_id=self.member_id,
            medicine_name="斯皮仁诺",
        )
        deleted_box_id = deleted_box.id
        deleted_box.soft_delete()

        plan = MedicationPlan.objects.create(
            user=self.user,
            member_id=self.member_id,
            drug_name="斯皮仁诺",
            frequency_type="daily",
            frequency_text="每天2次",
            reminder_times=[{"time": "18:00"}],
            start_date="2025-12-26",
            medicine_box_id=deleted_box_id,
        )

        response = self.client.patch(
            f"/api/v1/medical/resources/{plan.id}/?kind=medication-plans",
            {"frequency_text": "每天1次"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        plan.refresh_from_db()
        self.assertIsNone(plan.medicine_box_id)
        self.assertEqual(plan.frequency_text, "每天1次")
