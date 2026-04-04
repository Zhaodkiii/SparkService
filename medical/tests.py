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
                "client_uid": "11111111-1111-1111-1111-111111111111",
                "name": "成员A",
                "age": 32,
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
                "client_uid": "11111111-1111-1111-1111-111111111111",
                "name": "成员A-更新",
                "age": 33,
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
                "client_uid": "33333333-3333-3333-3333-333333333333",
                "name": "成员C",
                "age": 30,
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
                        "client_uid": "22222222-2222-2222-2222-222222222222",
                        "name": "成员B",
                        "age": 66,
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
                        "client_uid": "44444444-4444-4444-4444-444444444444",
                        "name": "成员D",
                        "age": 27,
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
