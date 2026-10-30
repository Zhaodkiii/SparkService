"""Explicit production reset, retaining superusers/configuration and every OSS object.

Run through the guarded maintenance procedure with application writers stopped.
Dry-run is the default; --apply requires --expected-plan from the reviewed dry-run.
No Django deletion signals: support deletion signals would schedule OSS deletion.
No TRUNCATE, foreign-key disabling, sequence reset, or OSS operations are used.
"""
import argparse
import hashlib
import json
import os
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, '/app' if Path('/app/manage.py').exists() else str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SparkService.settings')
import django
django.setup()
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.core.serializers.json import DjangoJSONEncoder


class MaintenanceEncoder(DjangoJSONEncoder):
    def default(self, obj):
        from zoneinfo import ZoneInfo
        if isinstance(obj, ZoneInfo): return str(obj)
        return super().default(obj)


def encode(value):
    return json.dumps(value, cls=MaintenanceEncoder, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def execute(apply=False, expected=None, test=False):
    if not test and (settings.MATERIAL_SYNC_ENVIRONMENT_ID != 'production' or connection.settings_dict['NAME'] != 'sparkservice'):
        raise RuntimeError('Only the verified production sparkservice database is allowed')
    models = [m for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy]
    existing = set(connection.introspection.table_names())
    models = [m for m in models if m._meta.db_table in existing]
    user_model = get_user_model()
    supers = set(user_model.objects.filter(is_superuser=True).values_list('pk', flat=True))
    if not supers:
        raise RuntimeError('No superuser to preserve')
    selected = defaultdict(set)
    complete_apps = {'diary_presets','material_library','font_library','diary_customizations','file_manager'}
    preserve = {
        'billing': {'RechargeProduct','CustomizationPackage','CustomizationPackageRevision'},
        'print_orders': {'Product','PaymentChannel','PaymentConfig','PaymentProbe'},
        'notification_center': {'NotificationTopic','NotificationBusinessScene','NotificationTemplate','NotificationTemplateVersion','ChannelTemplateVersion','AudienceDefinition'},
    }
    for m in models:
        app,name = m._meta.app_label,m.__name__
        qs = None
        if m == user_model:
            qs = m.objects.filter(is_superuser=False)
        elif app in complete_apps or (app in preserve and name not in preserve[app]):
            qs = m.objects.all()
        elif app == 'support_center' and name in {'Ticket','Message','Attachment','Operation','Audit','GarbageObject'}:
            qs = m.objects.all()
        elif app == 'accounts':
            fields = [f for f in m._meta.fields if f.is_relation and f.related_model == user_model]
            if fields:
                qs = m.objects.exclude(**{fields[0].attname+'__in':supers})
            else:
                qs = m.objects.all()
        elif app == 'ai_config' and name in {'TrialApplication','TrialApplicationRequest'}:
            qs = m.objects.all()
        if qs is not None:
            selected[m].update(qs.values_list('pk', flat=True))
    # Include all dependent rows even when on_delete is PROTECT; fail closed on
    # unforeseen configuration references rather than deleting configuration.
    config_labels = {m._meta.label for m in models if m._meta.app_label in preserve and m.__name__ in preserve[m._meta.app_label]}
    config_labels |= {'auth.Permission','auth.Group','contenttypes.ContentType','backoffice.AdminRole','backoffice.AdminPermission','backoffice.AdminRolePermission'}
    changed = True
    while changed:
        changed = False
        for m in models:
            for field in m._meta.fields:
                if not field.is_relation or not selected.get(field.related_model): continue
                refs = set(m.objects.filter(**{field.attname+'__in':selected[field.related_model]}).values_list('pk',flat=True))
                extra = refs-selected[m]
                if extra:
                    if m==user_model or m._meta.label in config_labels:
                        raise RuntimeError('Unreviewed protected reference: '+m._meta.label+'.'+field.name)
                    selected[m].update(extra);changed=True
    if selected[user_model] & supers:
        raise RuntimeError('Superuser would be deleted')
    selected = {m:ids for m,ids in selected.items() if ids}
    plan = {m._meta.label:sorted(map(str,ids)) for m,ids in selected.items()}
    plan_hash = fingerprint(plan)
    counts = {label:len(ids) for label,ids in plan.items()}
    protected = {}
    for m in models:
        qs=m.objects.exclude(pk__in=selected.get(m,()))
        protected[m] = fingerprint(list(qs.order_by('pk').values()))
    # Only break nullable edges participating in actual cycles. Clearing every
    # nullable FK would violate business checks (for example private-template owner).
    edges=[]
    for child in selected:
        for f in child._meta.fields:
            if f.is_relation and f.related_model in selected and child.objects.filter(
                    pk__in=selected[child],**{f.attname+'__in':selected[f.related_model]}).exists():
                edges.append((child,f.related_model,f))
    pending=set(selected);order=[];breaks=[]
    while pending:
        eligible=[m for m in pending if not any(parent==m and child in pending for child,parent,f in edges)]
        if eligible:
            order.extend(sorted(eligible,key=lambda m:m._meta.label));pending.difference_update(eligible)
            continue
        def reachable(start,goal):
            visited=set();queue=[start]
            while queue:
                node=queue.pop()
                if node==goal:return True
                if node in visited:continue
                visited.add(node)
                queue.extend(parent for child,parent,f in edges if child==node and parent in pending)
            return False
        edge=next((e for e in edges if e[0] in pending and e[1] in pending and e[2].null and reachable(e[1],e[0])),None)
        if edge is None:raise RuntimeError('Non-null relationship cycle; abort')
        breaks.append(edge);edges.remove(edge)
    report=dict(applied=False,plan_hash=plan_hash,delete_counts=counts,superusers_preserved=sorted(supers),oss_operations=0)
    if not apply:return report
    if expected!=plan_hash:raise RuntimeError('Plan changed; run and review dry-run again')
    with transaction.atomic():
        for m,parent,f in breaks:
            m.objects.filter(pk__in=selected[m],**{f.attname+'__in':selected[parent]}).update(**{f.attname:None})
        for m in order:
            m.objects.filter(pk__in=selected[m])._raw_delete('default')
        connection.check_constraints()
        for m,ids in selected.items():
            if m.objects.filter(pk__in=ids).exists():raise RuntimeError('Deletion incomplete: '+m._meta.label)
        for m,expected_hash in protected.items():
            if fingerprint(list(m.objects.order_by('pk').values()))!=expected_hash:
                raise RuntimeError('Preserved rows changed: '+m._meta.label)
        if set(user_model.objects.values_list('pk',flat=True))!=supers:
            raise RuntimeError('Unexpected users remain')
    report['applied']=True
    report['preserved_rows_verified']=True
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--expected-plan')
    args=p.parse_args()
    print(encode(execute(args.apply,args.expected_plan)))
