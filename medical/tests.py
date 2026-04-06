from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase


User = get_user_model()


class MedicalAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", email="tester@example.com", password="test123456")
        self.client.force_authenticate(self.user)

    def test_member_crud_and_etag(self):
        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {
                "name": "成员A",
                "gender": "female",
                "relationship": "self",
                "is_primary": True,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        member_id = create_resp.json()["data"]["id"]

        list_resp = self.client.get("/api/v1/medical/members/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.json()["code"], 0)
        etag = list_resp.headers.get("ETag")
        self.assertTrue(etag)

        not_modified_resp = self.client.get("/api/v1/medical/members/", HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(not_modified_resp.status_code, 304)

        update_resp = self.client.put(
            f"/api/v1/medical/members/{member_id}/",
            {
                "name": "成员A-更新",
                "gender": "female",
                "relationship": "self",
                "is_primary": True,
            },
            format="json",
        )
        self.assertEqual(update_resp.status_code, 200)

        delete_resp = self.client.delete(f"/api/v1/medical/members/{member_id}/")
        self.assertEqual(delete_resp.status_code, 200)

    def test_member_accepts_legacy_reference_timestamp_birth_date(self):
        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {
                "name": "成员C",
                "gender": "male",
                "relationship": "self",
                "birth_date": -149762397,
                "is_primary": False,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        member = create_resp.json()["data"]
        self.assertEqual(member["birth_date"], "1996-04-03")

    def test_sync_upload_and_bootstrap(self):
        upload_resp = self.client.post(
            "/api/v1/medical/sync/upload/",
            {
                "members": [
                    {
                        "name": "成员B",
                        "gender": "male",
                        "relationship": "father",
                        "is_primary": False,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(upload_resp.status_code, 200)

        bootstrap_resp = self.client.get("/api/v1/medical/sync/bootstrap/")
        self.assertEqual(bootstrap_resp.status_code, 200)
        payload = bootstrap_resp.json()
        self.assertEqual(payload["code"], 0)
        self.assertEqual(len(payload["data"]["members"]), 1)

    def test_sync_upload_accepts_legacy_reference_timestamp_birth_date(self):
        upload_resp = self.client.post(
            "/api/v1/medical/sync/upload/",
            {
                "members": [
                    {
                        "name": "成员D",
                        "gender": "male",
                        "relationship": "father",
                        "birth_date": -55154344,
                        "is_primary": False,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(upload_resp.status_code, 200)

        bootstrap_resp = self.client.get("/api/v1/medical/sync/bootstrap/")
        self.assertEqual(bootstrap_resp.status_code, 200)
        members = bootstrap_resp.json()["data"]["members"]
        self.assertTrue(any(member["birth_date"] == "1999-04-03" for member in members))

    def test_prescription_domain_crud_and_relations(self):
        member_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "成员E", "gender": "male", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]
        case_resp = self.client.post(
            "/api/v1/medical/cases/",
            {"member": member_id, "title": "高血压复诊"},
            format="json",
        )
        case_id = case_resp.json()["data"]["id"]

        batch_resp = self.client.post(
            "/api/v1/medical/prescription-batches/",
            {
                "member": member_id,
                "medical_case": case_id,
                "prescriber_name": "Dr.X",
                "institution_name": "Spark Hospital",
                "batch_no": "BATCH-001",
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(batch_resp.status_code, 201)
        batch_id = batch_resp.json()["data"]["id"]

        medication_resp = self.client.post(
            "/api/v1/medical/medications/",
            {
                "member": member_id,
                "batch": batch_id,
                "drug_name": "Metformin",
                "frequency_text": "每日两次",
                "reminder_times": ["08:00", "20:00"],
            },
            format="json",
        )
        self.assertEqual(medication_resp.status_code, 201)
        medication_id = medication_resp.json()["data"]["id"]

        taken_resp = self.client.post(
            "/api/v1/medical/medication-taken-records/",
            {
                "member": member_id,
                "medication": medication_id,
                "scheduled_at": "2026-04-06T08:00:00Z",
                "status": "scheduled",
                "dose_sequence": 1,
            },
            format="json",
        )
        self.assertEqual(taken_resp.status_code, 201)

        duplicate_resp = self.client.post(
            "/api/v1/medical/medication-taken-records/",
            {
                "member": member_id,
                "medication": medication_id,
                "scheduled_at": "2026-04-06T08:00:00Z",
                "status": "taken",
                "dose_sequence": 1,
            },
            format="json",
        )
        self.assertEqual(duplicate_resp.status_code, 400)

    def test_sync_upload_round_trip_for_medication_domain(self):
        upload_resp = self.client.post(
            "/api/v1/medical/sync/upload/",
            {
                "members": [{"id": 101, "name": "成员F", "gender": "female", "relationship": "self"}],
                "medical_cases": [{"id": 201, "member_id": 101, "title": "糖尿病管理"}],
                "prescription_batches": [{"id": 301, "member_id": 101, "medical_case_id": 201, "batch_no": "SYNC-B-1"}],
                "medications": [{"id": 401, "member_id": 101, "batch_id": 301, "drug_name": "Aspirin"}],
                "medication_taken_records": [
                    {
                        "id": 501,
                        "member_id": 101,
                        "medication_id": 401,
                        "scheduled_at": "2026-04-06T09:00:00Z",
                        "status": "taken",
                        "dose_sequence": 1,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(upload_resp.status_code, 200)

        bootstrap_resp = self.client.get("/api/v1/medical/sync/bootstrap/")
        self.assertEqual(bootstrap_resp.status_code, 200)
        data = bootstrap_resp.json()["data"]
        self.assertEqual(len(data["prescription_batches"]), 1)
        self.assertEqual(len(data["medications"]), 1)
        self.assertEqual(len(data["medication_taken_records"]), 1)
