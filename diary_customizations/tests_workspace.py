import uuid
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from . import tests as fixtures
from .models import Submission, Operation, Asset, Job, Request


class WorkspaceTests(TestCase):
    setUp=fixtures.CustomizationTests.setUp
    action=fixtures.CustomizationTests.action
    asset=fixtures.CustomizationTests.asset
    candidate=fixtures.CustomizationTests.candidate

    def submitted(self):
        a=self.asset()
        self.assertEqual(self.action('submit').status_code,200)
        return a,self.r.submissions.get()

    def supplement(self):
        a,sub=self.submitted()
        self.assertEqual(self.action('accept',{'submission_id':sub.pk},True).status_code,200)
        self.assertEqual(self.action('request-info',{'message':'请补充重要文字'},True).status_code,200)
        self.client.force_authenticate(self.a)
        self.assertEqual(self.action('edit',{'title':'新版主题','brief':{'description':'新的故事'}}).status_code,200)
        a.note='新版备注';a.must_use=True;a.save()
        self.assertEqual(self.action('submit').status_code,200)
        return a,sub,self.r.submissions.order_by('-number').first()

    def test_supplement_resumes_production_but_requires_explicit_new_basis(self):
        a,old,new=self.supplement()
        self.r.refresh_from_db();self.assertEqual(self.r.status,'in_production');self.assertEqual(self.r.accepted_submission_id,old.pk)
        self.client.force_authenticate(self.admin)
        detail=self.client.get(f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/').data
        self.assertTrue(detail['pending_submission']);self.assertIn('accept',detail['allowed_actions']);self.assertNotIn('deliver',detail['allowed_actions'])
        self.assertEqual(self.action('accept',{'submission_id':old.pk},True).status_code,409)
        self.assertEqual(self.action('accept',{'submission_id':new.pk},True).status_code,200)
        self.r.refresh_from_db();self.assertEqual(self.r.accepted_submission_id,new.pk)
        self.assertTrue(self.r.events.filter(action='basis_updated').exists())
        self.client.force_authenticate(self.a)
        owner=self.client.get(f'/api/v1/diary-customizations/requests/{self.r.pk}/').data
        self.assertEqual(owner['accepted_submission_id'],new.pk);self.assertFalse(owner['pending_submission'])
        self.assertNotIn('audit',owner);self.assertNotIn('internal_note',owner)

    def test_snapshot_display_and_urls_stay_bound_to_selected_submission(self):
        a,old,new=self.supplement()
        self.client.force_authenticate(self.admin)
        detail=self.client.get(f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/').data
        first,second=detail['submissions']
        self.assertEqual(first['snapshot']['title'],'私人主题');self.assertEqual(second['snapshot']['title'],'新版主题')
        self.assertEqual(first['resolved_assets'][0]['note'],'');self.assertEqual(second['resolved_assets'][0]['note'],'新版备注')
        self.assertFalse(first['resolved_assets'][0]['must_use']);self.assertTrue(second['resolved_assets'][0]['must_use'])
        self.assertIsNone(detail['assets'][0]['url'])
        outsider=Asset.objects.create(request=self.r,client_id=uuid.uuid4(),size=1,sha256='c'*64,mime='image/jpeg',status='ready',object_key='private')
        endpoint=f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/asset-urls/'
        response=self.client.post(endpoint,{'submission_id':old.pk,'asset_ids':[str(outsider.pk)]},format='json')
        self.assertEqual(response.status_code,400)
        a.object_key='traveldiary/customizations/photo';a.save()
        with patch('diary_customizations.storage.sign',return_value='https://photo.test'):
            response=self.client.post(endpoint,{'submission_id':old.pk,'asset_ids':[str(a.pk)]},format='json')
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['assets'][0]['url'],'https://photo.test')
        self.client.force_authenticate(self.b)
        self.assertEqual(self.client.post(f'/api/v1/diary-customizations/requests/{self.r.pk}/asset-urls/',{'asset_ids':[str(a.pk)]},format='json').status_code,404)

    def test_new_basis_abandons_old_inflight_delivery_jobs(self):
        a,old,new=self.supplement()
        j=Job.objects.create(request=self.r,actor=self.admin,submission=old,kind='delivery',size=1,sha256='e'*64,object_key='old',status='processing')
        self.assertEqual(self.action('accept',{'submission_id':new.pk},True).status_code,200)
        j.refresh_from_db();self.assertEqual(j.status,'abandoned');self.assertIsNone(j.lease)

    def test_pending_supplement_blocks_upload_and_delivery_of_old_basis(self):
        a,old,new=self.supplement()
        self.client.force_authenticate(self.admin)
        response=self.client.post(f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/delivery-uploads/',{'size':1,'sha256':'a'*64,'submission_id':old.pk},format='json')
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.action('deliver',{'delivery_id':str(uuid.uuid4()),'ios_reviewed':True},True).status_code,409)

    def test_transfer_requires_permission_and_does_not_emit_private_assignment_to_owner(self):
        self.submitted()
        inactive=get_user_model().objects.create_user(username='inactive',is_active=False)
        self.assertEqual(self.action('assign',{'assigned_to':self.b.pk},True).status_code,400)
        self.assertEqual(self.action('assign',{'assigned_to':inactive.pk},True).status_code,400)
        self.assertEqual(self.action('assign',{'assigned_to':self.admin.pk},True).status_code,200)
        self.r.refresh_from_db();self.assertEqual(self.r.assigned_to_id,self.admin.pk)
        self.assertFalse(self.r.events.filter(action='assignment_updated').exists())
        self.assertEqual(Operation.objects.get(action='assign').details['assigned_to'],self.admin.pk)

    def test_operation_status_is_scoped_to_actor_and_request(self):
        self.submitted();self.action('production',{'internal_note':'不能给用户看的备注'},True,key='stable-key')
        endpoint=f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/operations/?key=stable-key'
        response=self.client.get(endpoint);self.assertTrue(response.data['applied'])
        other=get_user_model().objects.create_superuser(username='second',email='second@example.test',password='x')
        self.client.force_authenticate(other);self.assertFalse(self.client.get(endpoint).data['applied'])
        self.client.force_authenticate(self.a);self.assertEqual(self.client.get(endpoint).status_code,403)

    def test_admin_list_supports_search_pending_tasks_assignment_and_overdue(self):
        self.supplement();self.r.refresh_from_db();self.r.due_at=timezone.now()-timedelta(days=1);self.r.save()
        self.client.force_authenticate(self.admin)
        endpoint='/api/admin/v1/diary-customizations/requests/'
        response=self.client.get(endpoint,{'task':'pending_info'})
        self.assertEqual(response.status_code,200);self.assertEqual(len(response.data['results']),1)
        self.assertEqual(response.data['summary']['pending_info'],1);self.assertEqual(response.data['summary']['overdue'],1)
        row=response.data['results'][0];self.assertTrue(row['overdue']);self.assertTrue(row['pending_submission'])
        for search in (row['number'],str(self.a.pk),'新版主题','owner'):
            response=self.client.get(endpoint,{'q':search});self.assertEqual(len(response.data['results']),1,response.data)
        self.assertEqual(len(self.client.get(endpoint,{'q':'not-found'}).data['results']),0)
        self.assertEqual(self.client.get(endpoint,{'q':'C99999999-aaaaaaaa'}).status_code,200)

    def test_conflict_preserves_server_data_and_can_be_retried_with_latest_revision(self):
        self.submitted();self.client.force_authenticate(self.admin)
        response=self.client.post(f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/production/',{'expected_revision':0,'internal_note':'过期编辑'},format='json',HTTP_IDEMPOTENCY_KEY='stale')
        self.assertEqual(response.status_code,409);self.r.refresh_from_db();self.assertEqual(self.r.internal_note,'')
        self.assertEqual(self.action('production',{'internal_note':'最新编辑'},True).status_code,200)

    def test_terminal_actions_and_user_cancel_request_availability(self):
        a,sub=self.submitted();self.action('accept',{'submission_id':sub.pk},True)
        self.action('cancel',{'message':'不再需要'})
        self.client.force_authenticate(self.a)
        response=self.client.get(f'/api/v1/diary-customizations/requests/{self.r.pk}/')
        self.assertNotIn('cancel',response.data['allowed_actions'])
        self.action('cancel',{'message':'同意取消'},True)
        self.client.force_authenticate(self.admin)
        detail=self.client.get(f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/').data
        self.assertEqual(detail['allowed_actions'],[])
        self.assertEqual(self.action('assign',{'assigned_to':self.admin.pk},True).status_code,409)

    def test_each_candidate_enforces_its_own_basis_and_must_use_photos(self):
        d=self.candidate();a=self.asset()
        d.submission.snapshot={'assets':[{'id':str(a.pk),'must_use':True}]};d.submission.save()
        self.assertEqual(self.action('deliver',{'delivery_id':str(d.pk),'ios_reviewed':True,'used_asset_ids':[]},True).status_code,400)
        self.assertEqual(self.action('deliver',{'delivery_id':str(d.pk),'ios_reviewed':False,'used_asset_ids':[str(a.pk)]},True).status_code,400)
        with patch('diary_customizations.storage.sign',return_value='https://example.test'):
            response=self.action('deliver',{'delivery_id':str(d.pk),'ios_reviewed':True,'used_asset_ids':[str(a.pk)]},True)
        self.assertEqual(response.status_code,200,response.data)
