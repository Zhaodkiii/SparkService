from unittest.mock import patch,MagicMock
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Config,Ticket,Message,Attachment,Category,Article,Operation
from datetime import timedelta

class SupportTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.user=U.objects.create_user(username='owner',password='pw',is_superuser=True)
        self.other=U.objects.create_user(username='other',password='pw')
        self.staff=U.objects.create_user(username='staff',password='pw',is_staff=True,is_superuser=True)
        Config.objects.create(accepting=True,service_hours='工作日处理')
        self.c=APIClient();self.c.force_authenticate(self.user)
        self.a=APIClient();self.a.force_authenticate(self.staff)
        self.payload=dict(title='导出失败',description='点击导出按钮后提示失败，无法生成图片。',kind='error',environment={'version':'1.0'},client_request_id='create-1')
    def create(self,key=None):
        d={**self.payload}
        if key:d['client_request_id']=key
        r=self.c.post('/api/v1/support/tickets/',d,format='json');self.assertEqual(r.status_code,201,r.data);return r.data
    def action(self,t,action,body='已核实处理结果，请再试一次',key='action-1',admin=True):
        c=self.a if admin else self.c
        prefix='/api/admin/v1/' if admin else '/api/v1/'
        return c.post(f'{prefix}support/tickets/{t["id"]}/actions/',dict(action=action,body=body,revision=t['revision'],client_request_id=key),format='json')
    def test_create_idempotent_and_content_conflict(self):
        t=self.create();r=self.c.post('/api/v1/support/tickets/',self.payload,format='json')
        self.assertEqual(r.status_code,200);self.assertEqual(r.data['id'],t['id']);self.assertEqual(Ticket.objects.count(),1)
        r=self.c.post('/api/v1/support/tickets/',{**self.payload,'title':'另一问题'},format='json');self.assertEqual(r.status_code,409)
    def test_private_isolation_and_no_internal_notes(self):
        t=self.create();url=f'/api/admin/v1/support/tickets/{t["id"]}/messages/'
        r=self.a.post(url,dict(body='这是内部记录',visibility='internal',revision=t['revision'],client_request_id='note'),format='json');self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.c.get(f'/api/v1/support/tickets/{t["id"]}/messages/').data['results'][0]['body'],self.payload['description'])
        self.assertEqual(len(self.c.get(f'/api/v1/support/tickets/{t["id"]}/messages/').data['results']),1)
        self.c.force_authenticate(self.other);self.assertEqual(self.c.get(f'/api/v1/support/tickets/{t["id"]}/').status_code,404)
    def test_full_workflow_unread_and_read_race(self):
        t=self.create();t=self.action(t,'request_info').data
        self.assertEqual(t['status'],'waiting_user');self.assertEqual(self.c.get('/api/v1/support/summary/').data['unread_ticket_count'],1)
        old_sequence=t['public_sequence']
        r=self.c.post(f'/api/v1/support/tickets/{t["id"]}/messages/',dict(body='已补充具体步骤',revision=t['revision'],client_request_id='reply'),format='json');self.assertEqual(r.status_code,200,r.data);t=r.data
        self.assertEqual(t['status'],'processing');t=self.action(t,'resolve',key='resolve').data;self.assertEqual(t['status'],'resolved')
        self.c.post(f'/api/v1/support/tickets/{t["id"]}/read/',dict(through_sequence=old_sequence),format='json')
        self.assertEqual(self.c.get('/api/v1/support/summary/').data['unread_ticket_count'],1)
        self.c.post(f'/api/v1/support/tickets/{t["id"]}/read/',dict(through_sequence=t['public_sequence']),format='json')
        self.assertEqual(self.c.get('/api/v1/support/summary/').data['unread_ticket_count'],0)
        r=self.action(t,'close',admin=False,key='close');self.assertEqual(r.data['status'],'closed')
        bad=self.c.post(f'/api/v1/support/tickets/{t["id"]}/messages/',dict(body='不能追加',revision=r.data['revision'],client_request_id='late'),format='json');self.assertEqual(bad.status_code,403)
    def test_revision_conflict_and_public_permission(self):
        t=self.create();self.action(t,'accept');r=self.action(t,'resolve',key='stale');self.assertEqual(r.status_code,409)
        self.c.force_authenticate(self.other);r=self.c.get('/api/admin/v1/support/tickets/');self.assertEqual(r.status_code,403)
    def test_draft_publication_is_atomic_and_unpublish(self):
        Category.objects.create(code='test',name='测试')
        r=self.a.post('/api/admin/v1/support/help/articles/',dict(category='test',title='保存作品',body='原始版本正文'),format='json');self.assertEqual(r.status_code,201,r.data);a=r.data
        self.assertEqual(len(self.c.get('/api/v1/support/help/articles/').data['results']),0)
        a=self.a.post(f'/api/admin/v1/support/help/articles/{a["id"]}/publish/',dict(revision=a['revision']),format='json').data
        a=self.a.patch(f'/api/admin/v1/support/help/articles/{a["id"]}/',dict(category='test',title='改名',body='尚未发布正文',revision=a['revision']),format='json').data
        self.assertEqual(self.c.get(f'/api/v1/support/help/articles/{a["id"]}/').data['body'],'原始版本正文')
        self.a.post(f'/api/admin/v1/support/help/articles/{a["id"]}/unpublish/',dict(revision=a['revision']),format='json')
        self.assertEqual(self.c.get(f'/api/v1/support/help/articles/{a["id"]}/').status_code,410)
    def test_attachments_cannot_be_stolen_or_rebound(self):
        asset=Attachment.objects.create(owner=self.other,mime='image/png',size=10,status='ready',expires_at=timezone.now()+timedelta(minutes=30))
        r=self.c.post('/api/v1/support/tickets/',{**self.payload,'attachments':[str(asset.pk)]},format='json');self.assertEqual(r.status_code,400)
        self.assertEqual(Ticket.objects.count(),0)
        asset.owner=self.user;asset.save();t=self.create()
        self.assertEqual(self.c.get(f'/api/v1/support/attachments/{asset.pk}/url/').status_code,404)
    def test_outbox_only_public_updates(self):
        from notification_center.models import NotificationOutbox
        t=self.create();self.assertEqual(NotificationOutbox.objects.filter(event_type='notification.support.dispatch').count(),0)
        t=self.action(t,'resolve').data
        self.assertEqual(NotificationOutbox.objects.filter(event_type='notification.support.dispatch').count(),1)
    def test_pause_existing_work_continues(self):
        t=self.create();Config.objects.update(accepting=False)
        r=self.c.post('/api/v1/support/tickets/',{**self.payload,'client_request_id':'pause'},format='json');self.assertEqual(r.status_code,503)
        self.assertEqual(self.action(t,'resolve').status_code,200)
    def test_staff_scoping_assignment_and_private_contact(self):
        p=get_user_model().objects.create_user(username='agent',is_staff=True)
        p.user_permissions.add(*Permission.objects.filter(content_type__app_label='support_center',codename__in=['view_ticket','reply_ticket','assign_ticket']))
        t=self.create();a=APIClient();a.force_authenticate(p)
        self.assertEqual(a.get('/api/admin/v1/support/tickets/').status_code,200)
        r=a.post(f'/api/admin/v1/support/tickets/{t["id"]}/assign/',dict(assignee_id=p.pk,revision=t['revision'],client_request_id='claim'),format='json');self.assertEqual(r.status_code,200,r.data)
        Ticket.objects.filter(pk=t['id']).update(assignee=self.staff)
        self.assertEqual(a.get(f'/api/admin/v1/support/tickets/{t["id"]}/').status_code,404)
    def test_submission_recovery_is_owner_scoped(self):
        t=self.create();r=self.c.get('/api/v1/support/submission/?client_request_id=create-1');self.assertEqual(r.data['ticket']['id'],t['id'])
        self.c.force_authenticate(self.other);self.assertIsNone(self.c.get('/api/v1/support/submission/?client_request_id=create-1').data['ticket'])
    def test_bound_attachment_cannot_be_reused_and_private_url_is_scoped(self):
        asset=Attachment.objects.create(owner=self.user,mime='image/png',size=10,status='ready',expires_at=timezone.now()+timedelta(minutes=30))
        r=self.c.post('/api/v1/support/tickets/',{**self.payload,'attachments':[str(asset.pk)]},format='json');self.assertEqual(r.status_code,201,r.data)
        r=self.c.post('/api/v1/support/tickets/',{**self.payload,'client_request_id':'another','attachments':[str(asset.pk)]},format='json');self.assertEqual(r.status_code,400)
        self.c.force_authenticate(self.other);self.assertEqual(self.c.get(f'/api/v1/support/attachments/{asset.pk}/url/').status_code,404)
    @patch('diary_presets.storage.bucket')
    def test_upload_complete_checks_metadata(self,bucket):
        bucket.return_value.sign_url.return_value='https://test.oss-cn.aliyuncs.com/private'
        r=self.c.post('/api/v1/support/uploads/',dict(mime='image/jpeg',size=10),format='json');self.assertEqual(r.status_code,201,r.data);key=r.data['id']
        bucket.return_value.head_object.return_value=MagicMock(content_length=11,headers={'Content-Type':'image/jpeg'})
        self.assertEqual(self.c.post(f'/api/v1/support/uploads/{key}/complete/',{},format='json').status_code,400)
        bucket.return_value.head_object.return_value=MagicMock(content_length=10,headers={'Content-Type':'image/jpeg'})
        self.assertEqual(self.c.post(f'/api/v1/support/uploads/{key}/complete/',{},format='json').status_code,200)
    def test_invalid_attachment_identifier_is_validation_error(self):
        t=self.create();r=self.c.post(f'/api/v1/support/tickets/{t["id"]}/messages/',dict(body='测试附件',attachments=['bad-id'],revision=t['revision'],client_request_id='bad'),format='json');self.assertEqual(r.status_code,400,r.data)
    def test_redaction_hides_body_and_revokes_attachment(self):
        t=self.create();m=Message.objects.get(ticket_id=t['id']);r=self.a.post(f'/api/admin/v1/support/tickets/{t["id"]}/redactions/',dict(message_id=str(m.pk),reason='用户请求移除私人内容',revision=t['revision'],client_request_id='redact'),format='json');self.assertEqual(r.status_code,200)
        r=self.c.get(f'/api/v1/support/tickets/{t["id"]}/messages/');self.assertEqual(r.data['results'][0]['body'],'内容已隐藏')
    def test_deleting_account_keeps_durable_object_cleanup(self):
        from .models import GarbageObject
        a=Attachment.objects.create(owner=self.other,mime='image/png',size=10,expires_at=timezone.now())
        key=a.key;self.other.delete();self.assertTrue(GarbageObject.objects.filter(key=key).exists())
    def test_help_rejects_unapproved_image_and_unsafe_links(self):
        Category.objects.create(code='safe',name='安全')
        for body in ['[链接](javascript:bad)','![图](https://untrusted.example/a.png)','<script>alert(1)</script>']:
            r=self.a.post('/api/admin/v1/support/help/articles/',dict(category='safe',title='文章',body=body),format='json');self.assertEqual(r.status_code,400,r.data)
    def test_new_ticket_limit_does_not_count_idempotent_retry(self):
        self.create('one');self.create('two');self.create('three')
        r=self.c.post('/api/v1/support/tickets/',{**self.payload,'client_request_id':'four'},format='json');self.assertEqual(r.status_code,429)
        r=self.c.post('/api/v1/support/tickets/',{**self.payload,'client_request_id':'three'},format='json');self.assertEqual(r.status_code,200)
    def test_resolved_ticket_cannot_be_accepted_again(self):
        t=self.create();t=self.action(t,'resolve').data
        self.assertNotIn('accept',t['allowed_actions']);self.assertNotIn('resolve',t['allowed_actions'])
        self.assertEqual(self.action(t,'accept',key='invalid-accept').status_code,403)
    def test_nonstaff_django_permission_does_not_grant_admin_access(self):
        self.other.user_permissions.add(*Permission.objects.filter(content_type__app_label='support_center',codename='view_ticket'))
        self.c.force_authenticate(self.other)
        self.assertEqual(self.c.get('/api/admin/v1/support/tickets/').status_code,403)
    def test_other_app_token_cannot_query_private_support(self):
        self.c.force_authenticate(self.other,token={'bundle_id':'unrelated.app'})
        self.assertEqual(self.c.get('/api/v1/support/tickets/').status_code,403)
    @patch('diary_presets.storage.bucket')
    def test_help_image_not_public_until_published(self,bucket):
        from .models import HelpImage
        img=HelpImage.objects.create(author=self.staff,mime='image/png',size=10,ready=True)
        url=f'/api/v1/support/help/images/{img.pk}/url/'
        self.assertEqual(self.c.get(url).status_code,404)
        c=Category.objects.create(code='image',name='示意图')
        Article.objects.create(category=c,live=True,published=dict(title='示意图',body=f'![示意](support-image:{img.pk})',summary='',language='zh-Hans'))
        bucket.return_value.sign_url.return_value='https://test.oss.aliyuncs.com/help'
        self.assertEqual(self.c.get(url).status_code,200)
    def test_seen_notification_is_suppressed(self):
        from notification_center.models import NotificationOutbox
        from .tasks import dispatch_notification
        t=self.create();t=self.action(t,'resolve').data
        self.c.post(f'/api/v1/support/tickets/{t["id"]}/read/',dict(through_sequence=t['public_sequence']),format='json')
        b=NotificationOutbox.objects.get(event_type='notification.support.dispatch')
        with patch('support_center.tasks.APNsProvider.send') as send:
            dispatch_notification(b.payload['intent_id'],b.payload['event_id'])
            send.assert_not_called()
        b.refresh_from_db();self.assertEqual(b.last_error,'already_seen')
    @patch('support_center.management.commands.cleanup_support.bucket')
    def test_cleanup_removes_abandoned_assets_but_protects_active_ticket(self,bucket):
        from django.core.management import call_command
        orphan=Attachment.objects.create(owner=self.other,mime='image/png',size=10,expires_at=timezone.now()-timedelta(hours=25))
        Attachment.objects.filter(pk=orphan.pk).update(created_at=timezone.now()-timedelta(hours=25))
        t=self.create();m=Message.objects.get(ticket_id=t['id'])
        active=Attachment.objects.create(owner=self.user,message=m,mime='image/png',size=10,expires_at=timezone.now()-timedelta(days=10))
        call_command('cleanup_support',execute=True,verbosity=0)
        self.assertFalse(Attachment.objects.filter(pk=orphan.pk).exists());self.assertTrue(Attachment.objects.filter(pk=active.pk).exists());bucket.return_value.delete_object.assert_called()
    @patch('support_center.management.commands.cleanup_support.bucket')
    def test_cleanup_preserves_images_in_article_version_history(self,bucket):
        from django.core.management import call_command
        from .models import HelpImage,ArticleVersion
        img=HelpImage.objects.create(author=self.staff,mime='image/png',size=10,ready=True)
        HelpImage.objects.filter(pk=img.pk).update(created_at=timezone.now()-timedelta(days=3))
        a=Article.objects.create(category=Category.objects.create(code='history',name='历史'),draft={},published={})
        ArticleVersion.objects.create(article=a,content={'body':f'![旧图](support-image:{img.pk})'})
        call_command('cleanup_support',execute=True,verbosity=0);self.assertTrue(HelpImage.objects.filter(pk=img.pk).exists())
    def test_reply_templates_do_not_require_configuration_privilege(self):
        p=get_user_model().objects.create_user(username='reply-only',is_staff=True)
        p.user_permissions.add(*Permission.objects.filter(content_type__app_label='support_center',codename='reply_ticket'))
        Config.objects.update(templates=['请补充复现步骤'])
        c=APIClient();c.force_authenticate(p)
        self.assertEqual(c.get('/api/admin/v1/support/reply-templates/').data,['请补充复现步骤'])
        self.assertEqual(c.get('/api/admin/v1/support/config/').status_code,403)
    def test_unsupported_detail_post_and_admin_creation_are_405(self):
        t=self.create();c=Category.objects.create(code='method',name='测试')
        a=Article.objects.create(category=c)
        self.assertEqual(self.a.post(f'/api/admin/v1/support/help/articles/{a.pk}/',{},format='json').status_code,405)
        self.assertEqual(self.a.post('/api/admin/v1/support/tickets/',self.payload,format='json').status_code,405)
    def test_public_submission_limits_match_actual_serializer_rules(self):
        from .views import TicketInput
        response=self.c.get('/api/v1/support/config/')
        limits=response.data['submission_limits'];fields=TicketInput().fields
        self.assertEqual(limits['description_min'],fields['description'].min_length)
        self.assertEqual(limits['description_max'],fields['description'].max_length)
        self.assertEqual(limits['title_max'],fields['title'].max_length)
        self.assertEqual(limits['attachments_max'],fields['attachments'].max_length)
    def test_six_character_description_returns_validation_error(self):
        response=self.c.post('/api/v1/support/tickets/',{**self.payload,'description':'就是不开心啊'},format='json')
        self.assertEqual(response.status_code,400)
        self.assertEqual(Ticket.objects.count(),0)
