from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from file_manager.models import ManagedFile
from medical.models import MedicationPlan, MedicineBox, Prescription

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
            "prescription": ("prescription", body["prescription_ids"][0]),
            "plan": ("medication_plan", body["medication_plan_ids"][0]),
        }
        for key, (business_type, business_id) in expected.items():
            files[key].refresh_from_db()
            self.assertEqual(files[key].business_type, business_type)
            self.assertEqual(files[key].business_id, str(business_id))
