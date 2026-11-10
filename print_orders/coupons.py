from django.db.models import Q
from django.utils import timezone
from .models import PrintCoupon


def available_coupons(owner, product):
    return PrintCoupon.objects.filter(owner=owner, expires_at__gt=timezone.now(),
                                      order__isnull=True).filter(Q(product=product) | Q(product__isnull=True)).order_by('expires_at', 'id')


def coupon_amount(coupon, product, pages):
    if product.free_printing:
        return 0
    base = product.base_fen + product.page_fen * min(pages, coupon.included_pages)
    return min(coupon.cap_fen, base * coupon.percent // 100)


def product_scope_label(product):
    return product.title if product else '不限印制规格'
