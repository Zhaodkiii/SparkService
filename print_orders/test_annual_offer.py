from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import PrintCampaign, Product


class AnnualOfferPresentationTests(TestCase):
    def test_offer_exposes_print_scope_and_validity_for_purchase_page(self):
        now = timezone.now()
        product = Product.objects.create(
            title='A5', active=True, proof_approved=True, paper='测试纸',
            binding='测试装订', base_fen=1000, page_fen=10, regions=['上海'], terms='测试')
        plan = PrintCampaign.objects.create(
            title='年费开通礼', source='annual', active=True,
            starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=30),
            product=product, annual_product_id='annual-test', cap_fen=8800,
            included_pages=20, valid_days=30, quota=9999)
        user = get_user_model().objects.create_user(username='annual-offer-reader')
        client = APIClient()
        client.force_authenticate(user)
        response = client.get('/api/v1/print/campaign/annual/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], plan.pk)
        self.assertEqual(response.data['included_pages'], 20)
        self.assertEqual(response.data['valid_days'], 30)
        self.assertEqual(response.data['ends_at'], plan.ends_at)
        self.assertEqual(response.data['cap_fen'], 8800)
