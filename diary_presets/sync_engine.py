"""Durable sync with OSS HEAD validation before a short production commit."""
from django.db import transaction
from django.utils import timezone
from .models import *
from .sync_protocol import *
# Same lease, task rendering and error semantics as the sticker sync module, isolated tables.
import uuid
from datetime import timedelta
from django.db.models import Q

def task_json(t):
    return dict(id=str(t.pk),library_id=str(t.library_uuid),source_version=t.source_version,
                content_hash=t.content_hash,state=t.state,commit_status=t.commit_status,result=t.result,
                expires_at=t.expires_at,updated_at=t.updated_at,created_at=t.created_at)


def fail(t, error):
    t.refresh_from_db()
    if t.commit_status=='committed':
        t.state='committed_verification_pending'
    else:
        t.state='conflict' if not error.retryable else 'failed'
    t.result={**t.result,'error_code':error.code,'message':error.message,'retryable':error.retryable}
    t.save(update_fields=['state','result','updated_at'])


@transaction.atomic
def claim(pk):
    now=timezone.now();token=uuid.uuid4().hex
    task=PresetSyncTask.objects.get(pk=pk)
    if task.side=='target':
        PresetSyncSlot.objects.get_or_create(library_uuid=uuid.UUID(int=0))
        PresetSyncSlot.objects.select_for_update().get(pk=uuid.UUID(int=0))
        if PresetSyncTask.objects.filter(side='target',lease_until__gt=now).count()>=2:return None
    updated=PresetSyncTask.objects.filter(pk=pk).filter(Q(lease_until__isnull=True)|Q(lease_until__lt=now)).update(lease_until=now+timedelta(seconds=90),lease_token=token)
    return token if updated else None


def heartbeat(pk, token, **updates):
    if not PresetSyncTask.objects.filter(pk=pk,lease_token=token).update(lease_until=timezone.now()+timedelta(seconds=90),updated_at=timezone.now(),**updates):
        raise SyncError('LEASE_LOST','任务已交由其他执行器处理',True)



def receiver_preflight(t,token):
    inspect_target(t.snapshot)
    verify_resources(t.snapshot,lambda n,total:heartbeat(t.pk,token,result={'checked':n,'total':total}))
    result=inspect_target(t.snapshot)
    t.refresh_from_db();t.result=result;t.baseline=result['target_fingerprint'];t.state='ready'
    t.expires_at=timezone.now()+timedelta(minutes=10);t.save()


def receiver_import(t, token):
    if t.commit_status == 'committed':
        verify_committed(t)
        return
    s = t.snapshot
    heartbeat(t.pk, token, state='checking')
    verify_resources(s, lambda n,total: heartbeat(t.pk,token,result={'checked':n,'total':total}))
    PresetSyncSlot.objects.get_or_create(library_uuid=t.library_uuid)
    from material_library.models import (MaterialLibrary, Material, MaterialRevision, ResourceBlob, LibraryVersion,
        LibraryItem, LibraryDraft, TemplateLibraryBinding, TemplateMaterialLink)
    from billing.models import ContentOffer, ContentPolicyRevision
    with transaction.atomic():
        PresetSyncSlot.objects.select_for_update().get(pk=t.library_uuid)
        locked = PresetSyncTask.objects.select_for_update().get(pk=t.pk)
        if locked.lease_token != token:
            raise SyncError('LEASE_LOST','任务执行租约已改变',True)
        if locked.commit_status == 'committed': return
        template = Template.objects.select_for_update().filter(pk=t.library_uuid).first()
        list(Series.objects.select_for_update().filter(slug=s['series']['slug']))
        library_ids = [l['id'] for l in s['libraries']]
        list(MaterialLibrary.objects.select_for_update().filter(pk__in=library_ids).order_by('pk'))
        list(LibraryDraft.objects.select_for_update().filter(library_id__in=library_ids).order_by('pk'))
        list(Material.objects.select_for_update().filter(pk__in=[i['material_id'] for l in s['libraries'] for i in l['items']]).order_by('pk'))
        list(SearchTaxon.objects.select_for_update().filter(pk__in=[x['id'] for x in s['taxa']]).order_by('pk'))
        offer = ContentOffer.objects.select_for_update().filter(target_kind='template',target_id=t.library_uuid).first()
        actual = inspect_target(s)
        if actual['target_fingerprint'] != t.baseline:
            raise SyncError('TARGET_CHANGED','生产模板、配套素材或价格在预检后变化，请重新检查')
        if not actual['no_op']:
            series,_ = Series.objects.get_or_create(slug=s['series']['slug'], defaults={k:v for k,v in s['series'].items() if k!='slug'})
            for row in s['taxa']:
                SearchTaxon.objects.get_or_create(pk=row['id'], defaults={k:v for k,v in row.items() if k not in ('id','parent_id','merged_into_id')})
            for row in s['taxa']:
                SearchTaxon.objects.filter(pk=row['id']).update(parent_id=row['parent_id'],merged_into_id=row['merged_into_id'])
            if not template:
                template = Template(id=t.library_uuid, series=series)
            for field in ('title','description','position','content_kind'):
                setattr(template, field, s['book'][field])
            template.series=series
            template.active=True
            template.revision+=1
            template.draft=s['book']['snapshot']
            template.save()
            version=template.current if actual['adopt_existing'] else Version.objects.create(template=template,number=s['source_version'],snapshot=s['book']['snapshot'])
            for blob in s['resources']:
                ResourceBlob.objects.get_or_create(pk=blob['sha256'], defaults={k:v for k,v in blob.items() if k!='sha256'})
            new_links={}
            for spec in s['libraries']:
                library,created=MaterialLibrary.objects.get_or_create(pk=spec['id'], defaults={
                    'template_id':spec['template_id'],'library_type':spec['type'],'title':spec['title']})
                lv=library.versions.filter(number=spec['version']).first()
                if not lv:
                    revisions=[]
                    for item in spec['items']:
                        material,_=Material.objects.get_or_create(pk=item['material_id'],defaults={
                            'source_identity':item['source_identity'],'material_type':spec['type']})
                        data=item['revision']
                        rev=next((r for r in material.revisions.all() if revision_fields(r)==data),None)
                        if not rev:
                            values={k:v for k,v in data.items() if k not in ('material_id','resource_sha256','thumbnail_sha256')}
                            values.update(resource_id=data['resource_sha256'],thumbnail_id=data['thumbnail_sha256'])
                            rev=MaterialRevision.objects.create(material=material,digest=digest(data),**values)
                        revisions.append(rev)
                    content=deepcopy(spec['content'])
                    if content: content['items']=[{'revision':r.pk} for r in revisions]
                    lv=LibraryVersion.objects.create(library=library,number=spec['version'],content=content,
                                                    preset_version=version if spec['template_id'] else None)
                    LibraryItem.objects.bulk_create([LibraryItem(version=lv,material=r.material,revision=r,position=i) for i,r in enumerate(revisions)])
                # Existing shared library current/drafts are not moved by a book import.
                if created:
                    library.current=lv;library.state_revision=1;library.first_published_at=timezone.now();library.save()
                    LibraryDraft.objects.create(library=library,base_version=lv.number,content=lv.content)
                TemplateLibraryBinding.objects.get_or_create(preset_version=version,library_type=spec['type'],defaults={'library_version':lv})
                new_links[spec['type']]=(library,lv)
            for kind in ('sticker','background'):
                library,lv=new_links.get(kind,(None,None))
                link,_=TemplateMaterialLink.objects.get_or_create(template=template,library_type=kind)
                link.library=library;link.library_version=lv;link.revision+=1;link.save()
            template.current=version;template.save(update_fields=['current'])
            from .search import index_version, bump
            index_version(template,version)
            bump()
        else:
            version=template.current
        if not offer and s['initial_policy']:
            offer=ContentOffer.objects.create(target_kind='template',target_id=template.pk,title=template.title,state='active')
            policy=ContentPolicyRevision.objects.create(offer=offer,revision=1,**s['initial_policy'],
                content_scope_snapshot={'target_kind':'template','target_id':str(template.pk),'scope':'personal_permanent'})
            offer.current_policy_revision=policy;offer.save()
        PresetSyncMapping.objects.get_or_create(source_environment=t.source_environment,library_uuid=template.pk,
            source_version=t.source_version,content_hash=t.content_hash,defaults={'target_version':version})
        Event.objects.create(template=template,action='production-sync',detail={
            'task_id':str(t.pk),'source_environment':t.source_environment,'source_version':t.source_version,
            'content_hash':t.content_hash,'pages':actual['count'],'libraries':actual['library_count']})
        locked.commit_status='committed';locked.state='committed'
        locked.result={**actual,'target_version':version.number,'message':'整本模板已原子提交'};locked.save()
        PresetSyncSlot.objects.filter(pk=t.library_uuid).update(active_task=None)
    t.refresh_from_db()
    verify_committed(t)


def verify_committed(t):
    template=Template.objects.select_related('current','series').get(pk=t.library_uuid)
    if snapshot_for(template)['content_hash']!=t.content_hash:
        raise SyncError('VERIFICATION_PENDING','生产已提交，整本及配套资源待核实',True)
    t.state='succeeded'
    t.result={**t.result,'target_version':template.current.number,
              'message':'整本模板、配套素材和搜索索引已发布，复用原 OSS 文件'}
    t.save(update_fields=['state','result','updated_at'])
