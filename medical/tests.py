import uuid

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from medical.models import ExaminationReport, Member

User = get_user_model()

UNIFIED_BASE = "/api/v1/medical/resources/"


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

    def test_prescription_workflow_save_with_nested_medications(self):
        member_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "成员F", "gender": "female", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]

        resp = self.client.post(
            "/api/v1/medical/workflows/prescriptions/save/",
            {
                "member": member_id,
                "prescriber_name": "Dr.Y",
                "institution_name": "Spark Hospital",
                "diagnosis": "上呼吸道感染",
                "batch_no": "WF-BATCH-001",
                "medications": [
                    {
                        "name": "阿莫西林",
                        "specification": "0.5g*12",
                        "dosage": "0.5g",
                        "frequency": "每日三次",
                        "duration": "7天",
                        "instructions": "饭后服用",
                    },
                    {
                        "drug_name": "布洛芬",
                        "dose_per_time": "0.2g",
                        "frequency_text": "必要时",
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()["data"]
        self.assertEqual(payload["batch"]["member"], member_id)
        self.assertEqual(len(payload["medications"]), 2)

        first_med = payload["medications"][0]
        self.assertEqual(first_med["drug_name"], "阿莫西林")
        self.assertEqual(first_med["strength"], "0.5g*12")
        self.assertEqual(first_med["dose_per_time"], "0.5g")
        self.assertEqual(first_med["frequency_text"], "每日三次")
        self.assertEqual(first_med["duration_days"], 7)

    def test_prescription_workflow_save_nested_medication_required_field_error(self):
        member_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "成员G", "gender": "male", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]

        resp = self.client.post(
            "/api/v1/medical/workflows/prescriptions/save/",
            {
                "member": member_id,
                "prescriber_name": "Dr.Z",
                "institution_name": "Spark Hospital",
                "batch_no": "WF-BATCH-002",
                "medications": [{"frequency": "每日一次"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotEqual(resp.json()["code"], 0)

    def test_health_exam_workflow_save_with_details(self):
        member_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "成员H", "gender": "male", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]

        resp = self.client.post(
            "/api/v1/medical/workflows/health-exams/save/",
            {
                "member": member_id,
                "institution_name": "苏州美健奥亚健康体检中心",
                "report_no": "B201600279",
                "exam_date": "2026-04-07",
                "exam_type": 1,
                "summary": "发现部分指标异常，建议复查。",
                "source": 2,
                "status": 1,
                "extra": {"source": "typed_upload"},
                "details": [
                    {
                        "category": "lab",
                        "sub_category": "血常规",
                        "item_name": "中性粒细胞百分数",
                        "result_value": "46.5",
                        "unit": "%",
                        "reference_range": "50.00-70.00",
                        "flag": "L",
                        "sort_order": 0,
                    },
                    {
                        "category": "imaging",
                        "subCategory": "甲状腺彩超",
                        "itemName": "甲状腺双叶囊肿（多发）",
                        "resultValue": "异常",
                        "bodyPart": "甲状腺",
                        "sortOrder": 1,
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()["data"]
        self.assertEqual(payload["id"], payload["report"]["id"])
        self.assertEqual(payload["report"]["institution_name"], "苏州美健奥亚健康体检中心")
        self.assertEqual(len(payload["details"]), 2)
        self.assertEqual(payload["details"][0]["item_name"], "中性粒细胞百分数")
        self.assertEqual(payload["details"][1]["body_part"], "甲状腺")

    def test_health_exam_workflow_save_allows_blank_institution_name(self):
        member_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "成员I", "gender": "female", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]

        resp = self.client.post(
            "/api/v1/medical/workflows/health-exams/save/",
            {
                "member": member_id,
                "institution_name": "",
                "report_no": "B201600280",
                "exam_date": "2026-04-07",
                "exam_type": 1,
                "source": 2,
                "status": 1,
                "extra": {"source": "typed_upload"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["report"]["institution_name"], "")

    def test_medical_report_workflow_create_uses_category_only_without_medical_case(self):
        member = Member.objects.create(user=self.user, name="成员J", gender="male", relationship="self")
        member_id = member.id

        resp = self.client.post(
            "/api/v1/medical/workflows/medical-reports/create/",
            {
                "member": member_id,
                "category": "imaging",
                "title": "胸部CT",
                "hospital": "测试医院",
                "doctor": "张医生",
                "content": "双肺纹理增多。",
                "date": "2026-04-07T10:00:00Z",
                "details": [
                    {
                        "category": "imaging",
                        "item_name": "胸部CT",
                        "result_value": "双肺纹理增多",
                        "sort_order": 0,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()["data"]
        self.assertEqual(payload["report"]["category"], "imaging")
        self.assertIsNone(payload["report"]["medical_record"])
        self.assertEqual(len(payload["details"]), 1)

    def test_workflow_create_symptom_visit_surgery_follow_up(self):
        member = Member.objects.create(user=self.user, name="成员K", gender="female", relationship="self")
        member_id = member.id
        case_resp = self.client.post(
            "/api/v1/medical/cases/",
            {"member": member_id, "title": "流程新建测试病例"},
            format="json",
        )
        self.assertEqual(case_resp.status_code, 201)
        case_id = case_resp.json()["data"]["id"]

        symptom_resp = self.client.post(
            "/api/v1/medical/workflows/symptoms/create/",
            {
                "member": member_id,
                "medical_case": case_id,
                "name": "头痛",
                "severity": "moderate",
                "started_at": "2026-04-10T08:00:00Z",
            },
            format="json",
        )
        self.assertEqual(symptom_resp.status_code, 201)
        self.assertIsNotNone(symptom_resp.json()["data"]["id"])

        visit_resp = self.client.post(
            "/api/v1/medical/workflows/visits/create/",
            {
                "member": member_id,
                "medical_case": case_id,
                "visit_type": "outpatient",
                "visited_at": "2026-04-10T09:30:00Z",
                "department": "neurology",
            },
            format="json",
        )
        self.assertEqual(visit_resp.status_code, 201)
        self.assertIsNotNone(visit_resp.json()["data"]["id"])

        surgery_resp = self.client.post(
            "/api/v1/medical/workflows/surgeries/create/",
            {
                "member": member_id,
                "medical_case": case_id,
                "procedure_name": "阑尾切除术",
                "performed_at": "2026-04-11T10:30:00Z",
                "surgeon": "Dr. Lee",
            },
            format="json",
        )
        self.assertEqual(surgery_resp.status_code, 201)
        self.assertIsNotNone(surgery_resp.json()["data"]["id"])

        follow_up_resp = self.client.post(
            "/api/v1/medical/workflows/follow-ups/create/",
            {
                "member": member_id,
                "medical_case": case_id,
                "planned_at": "2026-04-20T09:00:00Z",
                "status": "planned",
                "method": "phone",
                "outcome": "stable",
            },
            format="json",
        )
        self.assertEqual(follow_up_resp.status_code, 201)
        self.assertIsNotNone(follow_up_resp.json()["data"]["id"])

    def test_workflow_create_symptom_auto_creates_case_when_missing_medical_case(self):
        member = Member.objects.create(user=self.user, name="成员L", gender="male", relationship="self")
        member_id = member.id

        resp = self.client.post(
            "/api/v1/medical/workflows/symptoms/create/",
            {
                "member": member_id,
                "name": "发热",
                "severity": "mild",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()["data"]
        self.assertEqual(payload["member"], member_id)
        self.assertIsNotNone(payload["medical_case"])

    # --- Unified resource API (/resources/?kind=...) ---

    def test_unified_kind_required_and_invalid(self):
        r = self.client.get(UNIFIED_BASE)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["msg"], "kind_required")

        r2 = self.client.get(f"{UNIFIED_BASE}?kind=not-a-kind")
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r2.json()["msg"], "invalid_kind")
        self.assertIn("allowed_kinds", r2.json()["data"])

    def test_unified_rejects_unknown_query_params(self):
        r = self.client.get(f"{UNIFIED_BASE}?kind=members&foo=1")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["msg"], "invalid_query_params")
        self.assertIn("unknown_params", r.json()["data"])

    def test_unified_members_list_etag_matches_semantics(self):
        self.client.post(
            "/api/v1/medical/members/",
            {"name": "U1", "gender": "female", "relationship": "self", "is_primary": True},
            format="json",
        )
        list_resp = self.client.get(f"{UNIFIED_BASE}?kind=members")
        self.assertEqual(list_resp.status_code, 200)
        etag = list_resp.headers.get("ETag")
        self.assertTrue(etag)
        nm = self.client.get(f"{UNIFIED_BASE}?kind=members", HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(nm.status_code, 304)

    def test_unified_members_crud(self):
        c = self.client.post(
            f"{UNIFIED_BASE}?kind=members",
            {"name": "统一成员", "gender": "male", "relationship": "self", "is_primary": False},
            format="json",
        )
        self.assertEqual(c.status_code, 201)
        mid = c.json()["data"]["id"]

        g = self.client.get(f"{UNIFIED_BASE}{mid}/?kind=members")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["data"]["name"], "统一成员")

        u = self.client.patch(
            f"{UNIFIED_BASE}{mid}/?kind=members",
            {"name": "统一成员-改"},
            format="json",
        )
        self.assertEqual(u.status_code, 200)
        self.assertEqual(u.json()["data"]["name"], "统一成员-改")

        d = self.client.delete(f"{UNIFIED_BASE}{mid}/?kind=members")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.json()["data"]["id"], mid)

    def test_unified_medications_and_taken_records(self):
        member_resp = self.client.post(
            f"{UNIFIED_BASE}?kind=members",
            {"name": "U2", "gender": "female", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]
        case_resp = self.client.post(
            f"{UNIFIED_BASE}?kind=cases",
            {"member": member_id, "title": "统一病历"},
            format="json",
        )
        case_id = case_resp.json()["data"]["id"]
        batch_resp = self.client.post(
            f"{UNIFIED_BASE}?kind=prescription-batches",
            {
                "member": member_id,
                "medical_case": case_id,
                "prescriber_name": "Dr.U",
                "institution_name": "Unified Hospital",
                "batch_no": "UB-1",
                "status": "active",
            },
            format="json",
        )
        batch_id = batch_resp.json()["data"]["id"]

        med_resp = self.client.post(
            f"{UNIFIED_BASE}?kind=medications",
            {
                "member": member_id,
                "batch": batch_id,
                "drug_name": "UnifiedMed",
                "frequency_text": "qd",
                "reminder_times": [],
            },
            format="json",
        )
        self.assertEqual(med_resp.status_code, 201)
        med_id = med_resp.json()["data"]["id"]

        taken = self.client.post(
            f"{UNIFIED_BASE}?kind=medication-taken-records",
            {
                "member": member_id,
                "medication": med_id,
                "scheduled_at": "2026-04-07T10:00:00Z",
                "status": "scheduled",
                "dose_sequence": 1,
            },
            format="json",
        )
        self.assertEqual(taken.status_code, 201)
        tid = taken.json()["data"]["id"]

        one = self.client.get(f"{UNIFIED_BASE}{tid}/?kind=medication-taken-records")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["data"]["medication"], med_id)

    def test_unified_examination_report_accepts_medical_case_alias(self):
        member_resp = self.client.post(
            f"{UNIFIED_BASE}?kind=members",
            {"name": "U3", "gender": "male", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]
        case_resp = self.client.post(
            f"{UNIFIED_BASE}?kind=cases",
            {"member": member_id, "title": "检查案"},
            format="json",
        )
        case_id = case_resp.json()["data"]["id"]

        resp = self.client.post(
            f"{UNIFIED_BASE}?kind=examination-reports",
            {
                "member": member_id,
                "medical_case": case_id,
                "item_name": "CT 头部",
                "source": ExaminationReport.Source.MANUAL,
                "status": ExaminationReport.Status.DRAFT,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["medical_record"], case_id)

    def test_unified_prescription_batches_filter_by_medical_case_id(self):
        member_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "U4", "gender": "female", "relationship": "self"},
            format="json",
        )
        member_id = member_resp.json()["data"]["id"]
        case_resp = self.client.post(
            "/api/v1/medical/cases/",
            {"member": member_id, "title": "批次过滤"},
            format="json",
        )
        case_id = case_resp.json()["data"]["id"]
        self.client.post(
            "/api/v1/medical/prescription-batches/",
            {
                "member": member_id,
                "medical_case": case_id,
                "prescriber_name": "Dr.F",
                "institution_name": "H",
                "batch_no": "FB-1",
                "status": "active",
            },
            format="json",
        )
        r = self.client.get(
            f"{UNIFIED_BASE}?kind=prescription-batches&medical_case_id={case_id}"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["data"]), 1)

    def test_unified_med_exam_details_list_no_500_and_filters_by_member(self):
        """MedExamDetail 无 user 字段；统一入口 list 曾错误按 user 过滤导致 FieldError/500。"""
        member_resp = self.client.post(
            f"{UNIFIED_BASE}?kind=members",
            {"name": "明细统一", "gender": "female", "relationship": "self"},
            format="json",
        )
        self.assertEqual(member_resp.status_code, 201)
        member_id = member_resp.json()["data"]["id"]

        empty = self.client.get(f"{UNIFIED_BASE}?kind=med-exam-details&member_id={member_id}")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["code"], 0)
        self.assertEqual(empty.json()["data"], [])

        wf = self.client.post(
            "/api/v1/medical/workflows/health-exams/save/",
            {
                "member": member_id,
                "institution_name": "测试机构",
                "report_no": "R-UNIFIED-DETAIL",
                "exam_date": "2026-04-07",
                "exam_type": 1,
                "source": 2,
                "status": 1,
                "extra": {},
                "details": [
                    {
                        "category": "lab",
                        "item_name": "白细胞计数",
                        "result_value": "6.0",
                        "unit": "10^9/L",
                        "sort_order": 0,
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(wf.status_code, 201)
        report_id = wf.json()["data"]["id"]

        lst = self.client.get(f"{UNIFIED_BASE}?kind=med-exam-details&member_id={member_id}")
        self.assertEqual(lst.status_code, 200)
        rows = lst.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["business_id"], report_id)
        self.assertEqual(rows[0]["item_name"], "白细胞计数")
