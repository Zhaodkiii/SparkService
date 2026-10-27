"""Normalize deployment-owned sync settings; never print credentials or source values."""
import json
import os
from pathlib import Path
import shlex
import sys


def read_sync(path):
    values = {}
    if not path or not Path(path).exists():
        return values
    for line in Path(path).read_text().splitlines():
        line = line.strip().removeprefix('export ')
        key, sep, raw = line.partition('=')
        if sep and key.strip().startswith('MATERIAL_SYNC_'):
            parts = shlex.split(raw, comments=True)
            values[key.strip()] = ' '.join(parts)
    return values


def prepare(candidate, previous=None):
    path = Path(candidate)
    incoming = read_sync(candidate)
    existing = read_sync(previous)
    keys = {}
    for values in (existing, incoming):
        try:
            records = json.loads(values.get('MATERIAL_SYNC_ACCEPTED_KEYS', '{}'))
            if not isinstance(records, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('MATERIAL_SYNC_ACCEPTED_KEYS 格式无效，未生成生产配置') from None
        # Server-owned entries win over stale local copies; source pairing below is explicit.
        for key, record in records.items():
            if key in keys and keys[key] != record:
                raise ValueError('同名接收凭证不一致，请使用新 KEY_ID 轮换')
            keys.setdefault(key, record)
    key, secret = incoming.get('MATERIAL_SYNC_KEY_ID'), incoming.get('MATERIAL_SYNC_SECRET')
    source = incoming.get('MATERIAL_SYNC_ENVIRONMENT_ID', '')
    if key and secret and source and source != 'production':
        if key in keys and keys[key] != {'environment': source, 'secret': secret}:
            raise ValueError('同步凭证标识与生产记录不同，请使用新的 KEY_ID 轮换凭证')
        keys[key] = {'environment': source, 'secret': secret}
    values = {
        'MATERIAL_SYNC_ENVIRONMENT_ID': 'production',
        'MATERIAL_SYNC_SOURCE_ENABLED': 'false',
        'MATERIAL_SYNC_RECEIVER_ENABLED': 'true',
        'MATERIAL_SYNC_ACCEPTED_KEYS': "'" + json.dumps(keys, separators=(',', ':')) + "'",
        'MATERIAL_SYNC_KEY_ID': '',
        'MATERIAL_SYNC_SECRET': '',
        'MATERIAL_SYNC_TARGET_BASE_URL': '',
    }
    lines = [line for line in path.read_text().splitlines()
             if line.strip().removeprefix('export ').partition('=')[0].strip() not in values
             and line != '# 发布目标决定生产同步身份；本地原始 .env 保持不变。']
    temporary = path.with_name(path.name + '.production-next')
    temporary.write_text('\n'.join(lines) + '\n# 发布目标决定生产同步身份；本地原始 .env 保持不变。\n' +
                         '\n'.join(k + '=' + v for k, v in values.items()) + '\n')
    os.chmod(temporary, 0o600)
    temporary.replace(path)


if __name__ == '__main__':
    try:
        prepare(*sys.argv[1:])
    except (ValueError, OSError):
        raise SystemExit('生产同步配置生成失败：请检查配置格式及配对 KEY_ID，凭证内容不输出') from None
