from datetime import timedelta

from django.conf import settings
from django.test import SimpleTestCase


class TokenLifetimeConfigurationTests(SimpleTestCase):
    def test_refresh_token_lifetime_is_thirty_days(self):
        self.assertEqual(
            settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
            timedelta(days=30),
        )
