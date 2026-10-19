import hashlib
import json
import math
from rest_framework.exceptions import APIException, ValidationError
from rest_framework import serializers


class Conflict(APIException):
    status_code = 409
    default_detail = '订单已变化，请刷新后重试'


class Unavailable(APIException):
    status_code = 503
    default_detail = '印制服务暂不可用，请稍后重试'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class AddressInput(serializers.Serializer):
    name = serializers.CharField(max_length=60)
    phone = serializers.RegexField(r'^\+?[0-9 -]{7,20}$')
    region = serializers.CharField(max_length=120)
    detail = serializers.CharField(max_length=240)


class FileInput(serializers.Serializer):
    role = serializers.ChoiceField(choices=['interior', 'cover'])
    sha256 = serializers.RegexField(r'^[0-9a-f]{64}$')
    size = serializers.IntegerField(min_value=1, max_value=512 * 1024 * 1024)
    page_count = serializers.IntegerField(min_value=1, max_value=500)


class PageInput(serializers.Serializer):
    page_id = serializers.UUIDField()
    revision_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=['shell', 'interior'])


class SnapshotInput(serializers.Serializer):
    book_id = serializers.UUIDField()
    catalog_revision = serializers.UUIDField()
    pages = PageInput(many=True, min_length=1, max_length=501)
    exporter_version = serializers.ChoiceField(choices=['print-v1'])


class OrderInput(serializers.Serializer):
    key = serializers.UUIDField()
    revise_order_id = serializers.UUIDField(required=False)
    order_revision = serializers.IntegerField(min_value=1, required=False)
    product_id = serializers.UUIDField()
    product_revision = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=120)
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    page_count = serializers.IntegerField(min_value=1, max_value=500)
    address = AddressInput()
    snapshot = SnapshotInput()
    files = FileInput(many=True, min_length=1, max_length=2)
    confirmed = serializers.BooleanField()
    quote_total_fen = serializers.IntegerField(min_value=0)


def spec(product):
    fields = ('title', 'revision', 'width_mm', 'height_mm', 'paper', 'binding', 'description',
              'cover_mode', 'duplex', 'min_pages', 'max_pages', 'max_quantity', 'base_fen',
              'free_printing', 'page_fen', 'shipping_fen', 'regions', 'lead_time', 'terms')
    return dict(id=str(product.id), **{k: getattr(product, k) for k in fields})


def quote(product, count, quantity, region):
    if not product.active or not product.proof_approved:
        raise ValidationError('该规格尚未开放印制')
    if not product.min_pages <= count <= product.max_pages or not 1 <= quantity <= product.max_quantity:
        raise ValidationError('页数或份数超出此规格限制')
    if region not in product.regions:
        raise ValidationError('此收货地区暂不支持配送，请选择支持的地区')
    sheets = math.ceil(count / 2) if product.duplex else count
    total = (0 if product.free_printing else (product.base_fen + product.page_fen * count) * quantity) + product.shipping_fen
    if total <= 0 and not product.free_printing:
        raise ValidationError('商品价格尚未配置')
    return dict(total_fen=total, production_fen=total-product.shipping_fen,
                shipping_fen=product.shipping_fen, page_count=count, sheets=sheets, quantity=quantity)


def validate_manifest(data):
    files = data['files']
    roles = [f['role'] for f in files]
    if len(set(roles)) != len(roles) or 'interior' not in roles:
        raise ValidationError('必须提供内页 PDF，各文件角色不能重复')
    if next(f for f in files if f['role']=='interior')['page_count'] != data['page_count']:
        raise ValidationError('内页页数不一致')
    pages = data['snapshot']['pages']
    ids = [str(p['page_id']) for p in pages]
    shell = [p for p in pages if p['role']=='shell']
    if len(set(ids)) != len(ids) or len(shell) > 1 or (shell and pages[0]['role'] != 'shell'):
        raise ValidationError('页面不能重复，外壳最多一页并须位于最前面')
    covers = [f for f in files if f['role']=='cover']
    if bool(shell) != bool(covers) or (covers and covers[0]['page_count'] != 1):
        raise ValidationError('有外壳时单独交付一面外壳 PDF，无外壳时仅交付内页')
    inner = sum(p['role']=='interior' for p in pages)
    if inner < 1 or data['page_count'] not in (inner, inner + inner % 2):
        raise ValidationError('印刷页数与页面映射不一致')
    if not data['confirmed']:
        raise ValidationError('请检查并确认生产稿')
