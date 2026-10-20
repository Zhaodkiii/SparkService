"""Portable package validation used exclusively by the OSS-region processor."""
import hashlib
import json
import math
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_TOTAL = 2 * 1024**3
MAX_FILE = 100_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(path):
    if not isinstance(path, str) or not path or '\\' in path or ':' in path or path.startswith('/') or any(p in ('..', '.', '') for p in path.split('/')):
        raise ValueError('Unsafe file path')
    return path


def load_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON')))


def process_archive(archive, directory, namespace, put, private_request_id=None):
    """put(data, MIME) -> immutable OSS key. Never called from Django API."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    paths = set()
    total = 0
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > 10001:
            raise ValueError('Too many files')
        for info in z.infolist():
            if info.is_dir():
                relative(info.filename.rstrip('/'))
                continue
            path = relative(info.filename)
            if path in paths or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Duplicate path or symlink')
            if info.file_size > max(1, info.compress_size) * 1000:
                raise ValueError('Suspicious archive compression ratio')
            if info.file_size > MAX_FILE:
                raise ValueError('File too large')
            total += info.file_size
            if total > MAX_TOTAL:
                raise ValueError('Expanded archive too large')
            paths.add(path)
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            # ZipFile validates CRC; limit the read as well as advertised metadata.
            with z.open(info) as stream:
                data = stream.read(MAX_FILE + 1)
            if len(data) != info.file_size or len(data) > MAX_FILE:
                raise ValueError('Invalid expanded size')
            dest.write_bytes(data)
    manifest = load_json((root / 'package.json').read_bytes())
    if private_request_id:
        if manifest.get('audience') != 'private' or manifest.get('customizationRequestID') != str(private_request_id) or manifest.get('templateBookID') != 'custom-' + str(private_request_id):
            raise ValueError('Private package/request mismatch')
    elif manifest.get('audience') == 'private' or manifest.get('customizationRequestID') or str(manifest.get('templateBookID','')).startswith('custom-'):
        raise ValueError('Private packages cannot enter the public publisher')
    if manifest['format'] != 'TravelDiary.PresetBook' or manifest['schemaVersion'] != 1 or manifest['layerSchemaVersion'] not in (1, 2):
        raise ValueError('Unsupported package schema')
    if type(manifest.get('packageVersion')) is not int or manifest['packageVersion'] <= 0:
        raise ValueError('Invalid source package version')
    if not set(manifest['requiredCapabilities']) <= {'image', 'object', 'text', 'frame', 'drawing'}:
        raise ValueError('Unsupported capabilities')
    if not 1 <= len(manifest['pages']) <= 100:
        raise ValueError('Invalid page count')
    files = manifest['files']
    if len({f['path'] for f in files}) != len(files) or {f['path'] for f in files} != paths - {'package.json'}:
        raise ValueError('File index mismatch')
    for f in files:
        data = (root / relative(f['path'])).read_bytes()
        if len(data) != f['byteCount'] or digest(data) != f['sha256']:
            raise ValueError('File hash/size mismatch: ' + f['path'])
    assets = manifest['assetTable']
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 50_000_000
    image_paths = {a['path'] for a in assets.values()}
    pages = [load_json((root / relative(p['path'])).read_bytes()) for p in manifest['pages']]
    ids = [p['id'] for p in pages]
    if len(set(ids)) != len(ids) or ids != [p['id'] for p in manifest['pages']] or manifest['coverPageID'] not in ids:
        raise ValueError('Invalid page identities/cover')
    if manifest.get('shellPageID') and manifest['shellPageID'] not in ids:
        raise ValueError('Invalid shell page')
    for page in pages:
        if page['size'] != manifest['pageSize']:
            raise ValueError('Page size mismatch')
        image_paths.update(page['preview'].values())
    mime = {}
    for path in image_paths:
        if path not in paths:
            raise ValueError('Missing image')
        with Image.open(root / path) as image:
            if image.width * image.height > 100_000_000:
                raise ValueError('Image pixel limit exceeded')
            mime[path] = Image.MIME.get(image.format, 'application/octet-stream')
            image.verify()
    for aid, asset in assets.items():
        f = next((f for f in files if f['path'] == asset['path']), None)
        if asset['id'] != aid or not f or asset['sha256'] != f['sha256'] or asset['byteCount'] != f['byteCount']:
            raise ValueError('Asset index mismatch')
        with Image.open(root / asset['path']) as image:
            if asset['pixelSize'] != dict(width=image.width, height=image.height):
                raise ValueError('Asset dimensions mismatch')
    objects = {oid: load_json((root / relative(path)).read_bytes()) for oid, path in manifest['objectTable'].items()}
    if manifest['layerSchemaVersion'] >= 2:
        categories = {
            'background': {'paper_texture', 'page', 'scene'},
            'photo': {'slot', 'fixed', 'frame', 'photo_card'},
            'paper': {'note', 'checklist', 'route', 'ticket', 'title_card'},
            'text': {'title', 'body', 'date', 'quote', 'caption'},
            'illustration': {'scene', 'object', 'botanical', 'tape', 'stamp', 'ornament'},
            'branding': {'logo', 'seal', 'series_mark'},
        }
        for obj in objects.values():
            for layer in obj.get('layers', []):
                kind, subcategory, render_type = layer.get('kind'), layer.get('subcategory'), layer.get('renderType')
                if subcategory not in categories.get(kind, set()):
                    raise ValueError('Invalid layer semantic category')
                if render_type == 'group':
                    valid_render = bool(layer.get('contentID'))
                elif render_type == 'image':
                    valid_render = bool(layer.get('assetID'))
                elif render_type == 'native_text':
                    valid_render = kind == 'text' and layer.get('text') is not None
                elif render_type in ('canvas', 'frame'):
                    valid_render = True
                else:
                    valid_render = False
                if not valid_render:
                    raise ValueError('Invalid layer render type')
    closures = []
    for ref, page in zip(manifest['pages'], pages):
        needed = {ref['path'], *page['preview'].values()}
        def visit(oid, chain):
            if oid in chain or len(chain) >= 30 or oid not in objects:
                raise ValueError('Invalid object graph')
            obj = objects[oid]
            if obj['id'] != oid:
                raise ValueError('Object identity mismatch')
            needed.add(manifest['objectTable'][oid])
            layer_ids = [layer['id'] for layer in obj['layers']]
            if len(layer_ids) != len(set(layer_ids)):
                raise ValueError('Duplicate layer IDs')
            if obj.get('primaryLayerID') and obj['primaryLayerID'] not in layer_ids:
                raise ValueError('Missing primary layer')
            if obj.get('drawingPath'):
                needed.add(obj['drawingPath'])
            for layer in obj['layers']:
                if layer.get('frameTargetID') and layer['frameTargetID'] not in layer_ids:
                    raise ValueError('Missing frame target')
                if layer.get('assetID'):
                    needed.add(assets[layer['assetID']]['path'])
                if layer.get('contentID'):
                    visit(layer['contentID'], chain | {oid})
        visit(page['rootContentID'], set())
        if not needed <= paths:
            raise ValueError('Missing page dependencies')
        closures.append(needed)
    # Namespace IDs and paths so uploaded single-page packages merge without collisions.
    mapping = {p: namespace + '/' + p for p in paths if p != 'package.json'}
    for obj in objects.values():
        for identifier in [obj['id']] + [l['id'] for l in obj['layers']]:
            mapping[identifier] = namespace + '-' + identifier
    for identifier in ids + list(assets):
        mapping[identifier] = namespace + '-' + identifier
    def rewrite(value):
        if isinstance(value, str): return mapping.get(value, value)
        if isinstance(value, list): return [rewrite(v) for v in value]
        if isinstance(value, dict): return {mapping.get(k, k): rewrite(v) for k, v in value.items()}
        return value
    manifest = rewrite(manifest)
    keys = {}
    records = []
    for f in files:
        path = f['path']
        data = (root / path).read_bytes()
        if path.endswith('.json'):
            data = json.dumps(rewrite(load_json(data)), ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        key = put(data, mime.get(path, 'application/json' if path.endswith('.json') else 'application/octet-stream'))
        keys[mapping[path]] = key
        records.append(dict(path=mapping[path], byteCount=len(data), sha256=digest(data)))
    manifest['files'] = records
    record_map = {f['path']: f for f in records}
    for asset in manifest['assetTable'].values():
        asset.update(sha256=record_map[asset['path']]['sha256'], byteCount=record_map[asset['path']]['byteCount'])
    return dict(manifest=manifest, keys=keys, pages=[dict(data=rewrite(p), files=sorted(mapping[f] for f in closure)) for p, closure in zip(pages, closures)])
