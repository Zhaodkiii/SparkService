"""Export/merge configuration only. Run with Django initialized; never exports users or orders.

Export may contain AI credentials: use a private directory and never commit its output.
Import is restricted to a loopback database and rolls back unless --apply is supplied.
"""
import argparse
import json
import sys
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

# Ordered dependencies; natural keys prevent unrelated numeric IDs being overwritten.
SPECS = {
    'ai_runtime.Provider': ['id'],
    'ai_runtime.CredentialSlot': ['id'],
    'ai_runtime.CredentialVersion': ['slot_id', 'version'],
    'ai_runtime.Model': ['id'],
    'ai_runtime.Release': ['id'],
    'ai_runtime.Channel': ['id'],
    'ai_production.ProductionPolicy': ['name', 'effective_at'],
    'ai_production.ProductionControl': ['id'],
    'print_orders.Product': ['width_mm', 'height_mm'],
    'print_orders.PrintCampaign': ['title', 'source', 'starts_at'],
    'public_experience.InvitationCampaign': ['title', 'starts_at'],
    'notification_center.NotificationTopic': ['key'],
    'notification_center.NotificationBusinessScene': ['key'],
    'notification_center.NotificationTemplate': ['key'],
    'notification_center.NotificationTemplateVersion': ['template_id', 'version', 'locale'],
    'notification_center.ChannelTemplateVersion': ['template_version_id', 'channel', 'provider'],
    'support_center.Config': ['key'],
    'support_center.Category': ['code'],
    'support_center.Article': ['id'],
    'billing.RechargeProduct': ['rc_project_id', 'apple_product_id'],
    'billing.CustomizationPackage': ['code'],
    'billing.CustomizationPackageRevision': ['package_id', 'revision'],
}


def export():
    from ai_runtime.services import decrypt
    result = {}
    for label in SPECS:
        model = apps.get_model(label)
        rows = list(model.objects.order_by(model._meta.pk.name).values())
        if label == 'ai_runtime.CredentialVersion':
            for row in rows:
                row['secret'] = decrypt(model(**row))
                row.pop('ciphertext')
        result[label] = rows
    return result


def merge(data, apply=False):
    if settings.DATABASES['default']['HOST'] not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('Import requires a loopback database')
    from ai_runtime.services import encrypt, decrypt
    mapped, pending, report = {}, [], {}
    with transaction.atomic():
        for label, keys in SPECS.items():
            model = apps.get_model(label)
            stats = dict(created=0, updated=0, unchanged=0)
            for source in data[label]:
                row = dict(source)
                source_pk = row.pop(model._meta.pk.attname)
                if model._meta.pk.attname in keys:
                    row[model._meta.pk.attname] = source_pk
                deferred = {}
                for field in model._meta.fields:
                    if not field.is_relation:
                        continue
                    target = field.related_model._meta.label
                    value = row.get(field.attname)
                    if value is None:
                        continue
                    if target == settings.AUTH_USER_MODEL:
                        if not field.null:
                            raise RuntimeError('Non-null user reference in configuration')
                        row[field.attname] = None
                    elif (target, str(value)) in mapped:
                        row[field.attname] = mapped[target, str(value)]
                    elif target in SPECS and field.null:
                        deferred[field.attname] = (target, str(value))
                        row[field.attname] = None
                    else:
                        raise RuntimeError(f'Unresolved configuration dependency: {label}.{field.name}')
                secret = row.pop('secret', None)
                lookup = {key: row[key] for key in keys}
                matches = list(model.objects.filter(**lookup)[:2])
                if len(matches) > 1:
                    raise RuntimeError(f'Ambiguous natural key: {label}')
                obj = matches[0] if matches else None
                if label == 'ai_runtime.Release':
                    # Local release history has its own sequence; preserve existing bindings.
                    if obj:
                        row['sequence'] = obj.sequence
                    elif model.objects.filter(sequence=row['sequence']).exists():
                        from django.db.models import Max
                        row['sequence'] = model.objects.aggregate(n=Max('sequence'))['n'] + 1
                if secret is not None:
                    row['ciphertext'] = obj.ciphertext if obj and decrypt(obj) == secret else encrypt(secret)
                # Auto timestamps are preserved; comparison ignores their representation.
                changed = obj is None or any(
                    getattr(obj, key) != model._meta.get_field(key.removesuffix('_id') if key.endswith('_id') and key not in [f.name for f in model._meta.fields] else key).to_python(value)
                    for key, value in row.items()
                    if key not in deferred and key not in ('created_at', 'updated_at')
                )
                if obj is None:
                    obj = model.objects.create(**row)
                    model.objects.filter(pk=obj.pk).update(**row)
                    stats['created'] += 1
                elif changed:
                    model.objects.filter(pk=obj.pk).update(**row)
                    stats['updated'] += 1
                else:
                    stats['unchanged'] += 1
                mapped[label, str(source_pk)] = obj.pk
                if deferred:
                    pending.append((model, obj.pk, deferred))
                actual = model.objects.get(pk=obj.pk)
                for key, value in row.items():
                    if key in ('created_at', 'updated_at'):
                        continue
                    field = next(f for f in model._meta.fields if f.attname == key)
                    expected = field.target_field.to_python(value) if field.is_relation else field.to_python(value)
                    if getattr(actual, key) != expected:
                        raise RuntimeError(f'Verification mismatch: {label}.{key}')
            report[label] = stats
        for model, pk, deferred in pending:
            values = {key: mapped[target] for key, target in deferred.items()}
            model.objects.filter(pk=pk).update(**values)
            actual = model.objects.get(pk=pk)
            assert all(getattr(actual, key) == value for key, value in values.items())
        # Retain historical references while ensuring local-only activities cannot compete.
        for label, flag in [('print_orders.PrintCampaign', 'active'),
                            ('public_experience.InvitationCampaign', 'active'),
                            ('ai_runtime.Provider', 'enabled'),
                            ('ai_runtime.Model', 'enabled'),
                            ('ai_runtime.CredentialSlot', 'enabled')]:
            ids = [value for (kind, _), value in mapped.items() if kind == label]
            report[label]['disabled_local_only'] = apps.get_model(label).objects.exclude(pk__in=ids).filter(**{flag: True}).update(**{flag: False})
        if not apply:
            transaction.set_rollback(True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'import'])
    parser.add_argument('--input')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = export() if args.action == 'export' else merge(json.loads(Path(args.input).read_text()), args.apply)
    print(json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=False))


if __name__ == '__main__':
    import os
    import django
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SparkService.settings')
    django.setup()
    main()
