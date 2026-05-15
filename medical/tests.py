from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

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
